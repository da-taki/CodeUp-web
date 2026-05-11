"""
CodeUp — Full Test Suite
Covers: sandbox security, voice intent parsing, trace playback,
        snippet CRUD, size limits, repeat command, dotenv loading,
        pending quiz/bug intercepts, syntax checking, variable tracking,
        structure parsing, and execution story mode.
"""

import os
import sys
import json
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import app as app_module
from app import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_snippets(tmp_path, monkeypatch):
    """Redirect snippet storage to a temp file — never touches real snippets.json."""
    tmp_file = tmp_path / "snippets.json"
    tmp_file.write_text(json.dumps({"snippets": []}))
    monkeypatch.setenv("SNIPPETS_FILE", str(tmp_file))
    monkeypatch.setattr(app_module, "SNIPPETS_FILE", str(tmp_file))
    return tmp_file


@pytest.fixture
def client(tmp_snippets):
    """Flask test client with isolated snippet storage and AI disabled."""
    os.environ["GEMINI_ENABLED"] = "0"
    with app.test_client() as c:
        yield c
    os.environ["GEMINI_ENABLED"] = "1"


# ===========================================================================
# 1. ENVIRONMENT / CONFIG
# ===========================================================================

def test_gemini_disabled_returns_message(client):
    """When GEMINI_ENABLED=0, AI endpoints return a clear message not a crash."""
    res = client.post("/analyze", json={"code": "print(1)", "language": "en"})
    assert res.status_code == 200
    data = res.get_json()
    assert "analysis" in data
    assert "disabled" in data["analysis"].lower() or "service" in data["analysis"].lower()


def test_gemini_key_not_configured_returns_message(client, monkeypatch):
    """Missing API key returns a human-readable message not a 500."""
    monkeypatch.setenv("GEMINI_ENABLED", "1")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    res = client.post("/summarize", json={"code": "x = 1", "language": "en"})
    assert res.status_code == 200
    data = res.get_json()
    assert "summary" in data
    assert "configured" in data["summary"].lower() or "api" in data["summary"].lower()
    

# ===========================================================================
# 2. SANDBOX SECURITY
# ===========================================================================

@pytest.mark.parametrize("code, expected_fragments", [
    (
        "import os\nprint(os.getcwd())",
        ["not allowed", "import"],
    ),
    (
        "print(object.__subclasses__())",
        ["not allowed", "__subclasses__"],
    ),
    (
        "open('../outside.txt', 'w').write('x')",
        ["not defined", "open"],
    ),
    (
        "eval('import os')",
        ["not defined", "nameerror"],
    ),
    (
        "exec('import sys')",
        ["not defined", "nameerror"],
    ),
    (
        "compile('import os', '<s>', 'exec')",
        ["not defined", "nameerror"],
    ),
    (
        "__import__('os').system('ls')",
        ["not allowed", "os"],
    ),
])
def test_sandbox_blocks_escape_attempts(client, code, expected_fragments):
    """Sandbox must block all common escape patterns."""
    res = client.post("/run", json={"code": code})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is False
    error_lower = data["error"].lower()
    assert any(f in error_lower for f in expected_fragments), (
        f"Expected one of {expected_fragments!r} in:\n{data['error']}"
    )


def test_sandbox_input_blocked(client):
    """input() must be blocked with a clear explanation."""
    res = client.post("/run", json={"code": "x = input('name: ')\nprint(x)"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is False
    assert "input" in data["error"].lower() or (
        data.get("explanation") and "input" in data["explanation"].lower()
    )


def test_sandbox_allowed_modules(client):
    """math and random must be importable and usable."""
    res = client.post("/run", json={"code": "import math\nprint(int(math.pi))"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True, f"math import failed: {data.get('error')}"
    assert "3" in data.get("output", "")


def test_sandbox_normal_execution(client):
    """Basic arithmetic and print work correctly."""
    res = client.post("/run", json={"code": "print(2 + 2)"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "4" in data.get("output", "")


def test_sandbox_loop_output(client):
    """For loops produce correct sequential output."""
    res = client.post("/run", json={"code": "for i in range(3):\n    print(i)"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    output = data.get("output", "")
    assert "0" in output and "1" in output and "2" in output


# ===========================================================================
# 3. REQUEST SIZE LIMITS
# ===========================================================================

def test_max_code_size_rejected_run(client):
    """Code over MAX_CODE_SIZE must return 413 from /run."""
    big = "x = 1\n" * 20_000
    res = client.post("/run", json={"code": big})
    assert res.status_code == 413


def test_max_code_size_rejected_analyze(client):
    """Code over MAX_CODE_SIZE must return 413 from /analyze."""
    big = "x = 1\n" * 20_000
    res = client.post("/analyze", json={"code": big, "language": "en"})
    assert res.status_code == 413


def test_empty_code_rejected(client):
    """Empty code must return 400 from /run."""
    res = client.post("/run", json={"code": "   "})
    assert res.status_code == 400


def test_missing_body_handled(client):
    """Completely missing JSON body must not crash the server."""
    res = client.post("/run", data="not json", content_type="text/plain")
    assert res.status_code in (400, 413, 200)  # any of these is acceptable, not 500


# ===========================================================================
# 4. VOICE INTENT PARSING
# ===========================================================================

@pytest.mark.parametrize("voice_input, expected_action, check", [
    ("go to line fifteen",          "goto_line",    lambda d: d.get("line") == 15),
    ("go to line 3",                "goto_line",    lambda d: d.get("line") == 3),
    ("read line 7",                 "read_line",    lambda d: d.get("line") == 7),
    ("describe line 10",            "describe_line",lambda d: d.get("line") == 10),
    ("delete line 4",               "delete_line",  lambda d: d.get("line") == 4),
    ("clear editor",                "clear_editor", lambda d: True),
    ("summarize this file",         "summarize",    lambda d: True),
    ("advise on code",              "advise",       lambda d: True),
    ("next step",                   "next_step",    lambda d: True),
    ("previous step",               "previous_step",lambda d: True),
    ("what changed here",           "what_changed", lambda d: True),
    ("run",                         "run",          lambda d: True),
    ("fix code",                    "fix",          lambda d: True),
    ("check for errors",            "check_errors", lambda d: True),
    ("suggest next line",           "suggest_next", lambda d: True),
    ("story mode",                  "story_mode",   lambda d: True),
    ("learning mode",               "mentor_mode",  lambda d: True),
    ("bug challenge",               "bug_challenge",lambda d: True),
    ("save snippet named my prog",  "save_snippet_named", lambda d: "my prog" in d.get("name", "")),
    ("generate code for fibonacci", "generate_code",lambda d: "fibonacci" in d.get("prompt", "")),
    ("rename snippet 1234 to final","rename_snippet",lambda d: d.get("new_name") == "final"),
    ("quiz me on loops",            "quiz_me",      lambda d: "loops" in d.get("topic", "")),
    ("set breakpoint at line 5",    "set_breakpoint",lambda d: d.get("line_number") == 5),
    ("watch variable x",            "watch_variable",lambda d: d.get("variable") == "x"),
    ("insert function called greet","insert_function",lambda d: d.get("function_name") == "greet"),
    ("insert a for loop",           "insert_loop",  lambda d: True),
])
def test_voice_intent_parsing(client, voice_input, expected_action, check):
    if voice_input == "repeat":
        # Seed a run first so repeat has something to replay
        client.post("/voice-command", json={"text": "run"})

    res = client.post("/voice-command", json={"text": voice_input})
    assert res.status_code == 200
    data = res.get_json()
    assert data["action"] == expected_action, (
        f"Input {voice_input!r}: expected {expected_action!r}, got {data['action']!r}"
    )
    if check:
        assert check(data), f"Slot check failed for {voice_input!r}: {data}"


def test_voice_unknown_command(client):
    """Completely nonsense input resolves to unknown or confirm, never crashes."""
    res = client.post("/voice-command", json={"text": "xyzzy blort flibble"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["action"] in ("unknown", "confirm")


def test_voice_ambiguous_triggers_confirm(client):
    """Input that fuzzy-matches multiple commands should trigger confirm."""
    res = client.post("/voice-command", json={"text": "analyse"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["action"] in ("analyze", "confirm", "unknown")
    if data["action"] == "confirm":
        assert "options" in data
        assert len(data["options"]) >= 1


def test_voice_repeat_replays_last_action(client):
    """Repeat must return the same action as the previous command."""
    seed = client.post("/voice-command", json={"text": "execute code"})
    assert seed.get_json()["action"] == "run", f"Seed failed: {seed.get_json()}"

    repeat_res = client.post("/voice-command", json={"text": "repeat"})
    assert repeat_res.status_code == 200
    assert repeat_res.get_json()["action"] == "run"

def test_voice_empty_text(client):
    """Empty voice input must not crash."""
    res = client.post("/voice-command", json={"text": ""})
    assert res.status_code == 200
    data = res.get_json()
    assert "action" in data


# ===========================================================================
# 5. EXECUTION TRACE PLAYBACK
# ===========================================================================

@pytest.mark.timeout(15)
def test_trace_populated_after_run(client):
    """Running code must populate a non-empty trace."""
    res = client.post("/run", json={"code": "x = 5\ny = 10\nprint(x + y)"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert len(data.get("trace", [])) > 0, "Trace must not be empty after successful run"


@pytest.mark.timeout(15)
def test_trace_next_step_returns_speech(client):
    """next step voice command must return non-empty speech after a run."""
    run = client.post("/run", json={"code": "a = 1\nb = 2\nc = a + b"})
    assert run.get_json()["success"] is True
    assert len(run.get_json().get("trace", [])) > 0

    step = client.post("/voice-command", json={"text": "next step"})
    assert step.status_code == 200
    data = step.get_json()
    assert data["action"] == "next_step"
    assert data.get("speech"), f"Expected non-empty speech, got: {data}"


@pytest.mark.timeout(15)
def test_trace_step_counter_in_speech(client):
    """Speech output must contain 'Step X of Y' format."""
    run = client.post("/run", json={"code": "a = 1\nb = 2\nc = a + b"})
    run_data = run.get_json()
    assert run_data["success"] is True
    assert len(run_data.get("trace", [])) > 0, "Trace empty — cannot test step counter"

    step = client.post("/voice-command", json={"text": "next step"})
    speech = step.get_json().get("speech", "")
    assert "Step" in speech, f"Expected step counter in speech, got: {speech!r}"

@pytest.mark.timeout(15)
def test_trace_what_changed(client):
    """what changed must return speech after a run."""
    client.post("/run", json={"code": "x = 42\nprint(x)"})
    # advance to first step first
    client.post("/voice-command", json={"text": "next step"})
    res = client.post("/voice-command", json={"text": "what changed here"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["action"] == "what_changed"
    assert data.get("speech")


@pytest.mark.timeout(15)
def test_trace_endpoint_returns_structure(client):
    """GET /execution-trace must return expected keys."""
    client.post("/run", json={"code": "x = 1"})
    res = client.get("/execution-trace")
    assert res.status_code == 200
    data = res.get_json()
    assert "trace" in data
    assert "current_index" in data
    assert "duration_ms" in data


# ===========================================================================
# 6. SYNTAX CHECKING
# ===========================================================================

def test_syntax_check_clean_code(client):
    """Valid code returns has_errors=False."""
    res = client.post("/check-syntax", json={"code": "x = 1\nprint(x)"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["has_errors"] is False


def test_syntax_check_broken_code(client):
    """Broken code returns has_errors=True with error details."""
    res = client.post("/check-syntax", json={"code": "def foo(\n    print('oops')"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["has_errors"] is True
    assert data["error_count"] >= 1
    assert len(data["errors"]) >= 1
    assert "line" in data["errors"][0]
    assert "message" in data["errors"][0]


def test_syntax_check_empty_code(client):
    """Empty code returns has_errors=False cleanly."""
    res = client.post("/check-syntax", json={"code": ""})
    assert res.status_code == 200
    data = res.get_json()
    assert data["has_errors"] is False


# ===========================================================================
# 7. VARIABLE TRACKING
# ===========================================================================

def test_track_variables_basic(client):
    """Variable tracker finds assignments correctly."""
    code = "x = 5\ny = 10\nz = x + y"
    res = client.post("/track-variables", json={"code": code, "line": 1})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    names = [v["name"] for v in data["variables"]]
    assert "x" in names
    assert "y" in names


def test_track_variables_invalid_line(client):
    """Non-numeric line number returns 400."""
    res = client.post("/track-variables", json={"code": "x = 1", "line": "abc"})
    assert res.status_code == 400


def test_find_variable_usage(client):
    """Variable usage finder returns correct line numbers."""
    code = "x = 5\nprint(x)\ny = x + 1"
    res = client.post("/find-variable-usage", json={"code": code, "variable": "x"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["count"] >= 2
    lines = [u["line"] for u in data["usages"]]
    assert 1 in lines  # assignment


def test_find_variable_usage_not_found(client):
    """Variable not in code returns success=False with message."""
    res = client.post("/find-variable-usage", json={"code": "x = 1", "variable": "z"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is False
    assert "message" in data


# ===========================================================================
# 8. STRUCTURE PARSING
# ===========================================================================

def test_structure_functions(client):
    """Structure parser finds function definitions."""
    code = "def greet(name):\n    print(name)\n\ndef add(a, b):\n    return a + b"
    res = client.post("/structure", json={"code": code})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    fn_names = [f["name"] for f in data["structure"]["functions"]]
    assert "greet" in fn_names
    assert "add" in fn_names


def test_structure_classes(client):
    """Structure parser finds class definitions."""
    code = "class Dog:\n    def bark(self):\n        print('woof')"
    res = client.post("/structure", json={"code": code})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    class_names = [c["name"] for c in data["structure"]["classes"]]
    assert "Dog" in class_names


def test_structure_empty_code(client):
    """Empty code returns empty structure without error."""
    res = client.post("/structure", json={"code": ""})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert data["structure"]["functions"] == []
    assert data["structure"]["classes"] == []


# ===========================================================================
# 9. SNIPPET CRUD
# ===========================================================================

def test_snippet_save_and_list(client):
    """Save a snippet and confirm it appears in the list."""
    save = client.post("/snippets", json={"name": "test_snip", "code": "print('hi')"})
    assert save.status_code == 200
    data = save.get_json()
    assert data["success"] is True
    assert "id" in data
    assert "speech" in data

    lst = client.get("/snippets")
    assert lst.status_code == 200
    lst_data = lst.get_json()
    assert "snippets" in lst_data
    assert "speech" in lst_data
    names = [s["name"] for s in lst_data["snippets"]]
    assert "test_snip" in names


def test_snippet_delete(client):
    """Delete a snippet and confirm it no longer appears."""
    save = client.post("/snippets", json={"name": "to_delete", "code": "x = 1"})
    sid = save.get_json()["id"]

    delete = client.delete(f"/snippets/{sid}")
    assert delete.status_code == 200
    assert delete.get_json()["success"] is True

    lst = client.get("/snippets")
    names = [s["name"] for s in lst.get_json()["snippets"]]
    assert "to_delete" not in names


def test_snippet_update(client):
    """Update a snippet name via PUT."""
    save = client.post("/snippets", json={"name": "original", "code": "x = 1"})
    sid = save.get_json()["id"]

    update = client.put(f"/snippets/{sid}", json={"name": "renamed"})
    assert update.status_code == 200
    assert update.get_json()["success"] is True

    lst = client.get("/snippets")
    names = [s["name"] for s in lst.get_json()["snippets"]]
    assert "renamed" in names
    assert "original" not in names


def test_snippet_delete_nonexistent(client):
    """Deleting a nonexistent snippet returns success=True gracefully."""
    res = client.delete("/snippets/nonexistent-id-xyz")
    assert res.status_code == 200


def test_snippet_name_too_long(client):
    """Snippet name over 256 chars must return 400."""
    res = client.post("/snippets", json={"name": "x" * 300, "code": "print(1)"})
    assert res.status_code == 400


def test_snippet_code_too_large(client):
    """Snippet code over MAX_CODE_SIZE must return 413."""
    res = client.post("/snippets", json={"name": "big", "code": "x = 1\n" * 20_000})
    assert res.status_code == 413


def test_snippet_speech_single(client):
    """Single snippet produces grammatically correct speech."""
    client.post("/snippets", json={"name": "only_one", "code": "print(1)"})
    lst = client.get("/snippets")
    speech = lst.get_json()["speech"]
    assert "1 snippet" in speech


def test_snippet_speech_multiple(client):
    """Multiple snippets produce correct count in speech."""
    client.post("/snippets", json={"name": "first", "code": "print(1)"})
    client.post("/snippets", json={"name": "second", "code": "print(2)"})
    lst = client.get("/snippets")
    speech = lst.get_json()["speech"]
    assert "2 snippets" in speech


# ===========================================================================
# 10. LINE READING & DESCRIBE
# ===========================================================================

def test_read_line_context_valid(client):
    """Read line context returns correct line content."""
    code = "x = 5\ny = 10\nprint(x + y)"
    res = client.post("/read-line-context", json={"code": code, "line": 2})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "y" in data["content"]
    assert "indent_level" in data
    assert "context" in data


def test_read_line_context_invalid_line(client):
    """Non-numeric line returns 400."""
    res = client.post("/read-line-context", json={"code": "x = 1", "line": "bad"})
    assert res.status_code == 400


def test_read_line_context_out_of_range(client):
    """Line number beyond file length returns success=False."""
    res = client.post("/read-line-context", json={"code": "x = 1", "line": 999})
    assert res.status_code == 200
    assert res.get_json()["success"] is False


# ===========================================================================
# 11. SANDBOXED FILESYSTEM
# ===========================================================================

def test_fs_write_and_read(client):
    """Write then read a file in the sandbox."""
    write = client.post("/fs/write", json={"path": "test.txt", "content": "hello"})
    assert write.status_code == 200
    assert write.get_json()["success"] is True

    read = client.post("/fs/read", json={"path": "test.txt"})
    assert read.status_code == 200
    data = read.get_json()
    assert data["success"] is True
    assert data["content"] == "hello"


def test_fs_path_traversal_blocked(client):
    """Path traversal attempts must be blocked."""
    res = client.post("/fs/read", json={"path": "../../etc/passwd"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is False
    assert "outside" in data.get("error", "").lower() or "not found" in data.get("error", "").lower()


def test_fs_missing_path(client):
    """Missing path field returns 400."""
    res = client.post("/fs/read", json={})
    assert res.status_code == 400


def test_fs_delete(client):
    """Write then delete a file."""
    client.post("/fs/write", json={"path": "bye.txt", "content": "bye"})
    res = client.post("/fs/delete", json={"path": "bye.txt"})
    assert res.status_code == 200
    assert res.get_json()["success"] is True


def test_fs_info(client):
    """Workspace info endpoint returns expected keys."""
    res = client.get("/fs/info")
    assert res.status_code == 200
    data = res.get_json()
    assert "workspace" in data
    assert "total_files" in data


# ===========================================================================
# 12. SESSION ISOLATION
# ===========================================================================

def test_two_sessions_have_separate_traces():
    """Two clients with different session cookies get separate trace storage."""
    with app.test_client() as c1:
        r1 = c1.post("/run", json={"code": "x = 100\nprint(x)"})
        assert r1.get_json()["success"] is True

        t1 = c1.get("/execution-trace").get_json()
        assert isinstance(t1["trace"], list)
        assert len(t1["trace"]) > 0, "Session A must have trace after run"

    with app.test_client() as c2:
        t2 = c2.get("/execution-trace").get_json()
        assert isinstance(t2["trace"], list)
        assert len(t2["trace"]) == 0, "Fresh session must have empty trace"

# ===========================================================================
# 13. SEMANTIC ERROR CLASSIFICATION
# ===========================================================================

def test_semantic_issues_in_response(client):
    """Semantic issues key is always present in successful run response."""
    res = client.post("/run", json={"code": "x = 1\nprint(x)"})
    assert res.status_code == 200
    data = res.get_json()
    if data["success"]:
        assert "semantic_issues" in data
        assert isinstance(data["semantic_issues"], list)


# ===========================================================================
# 14. INTENT PARSER UNIT TESTS (direct, no HTTP)
# ===========================================================================

from intent_parser import parse_intent

@pytest.mark.parametrize("text, expected_intent, slot_check", [
    ("go to line twenty five",      "goto_line",    lambda s: s.get("line_number") == 25),
    ("go to line forty two",        "goto_line",    lambda s: s.get("line_number") == 42),
    ("read line 10",                "read_line",    lambda s: s.get("line_number") == 10),
    ("find function calculate",     "find_function",lambda s: s.get("function_name") == "calculate"),
    ("find class Parser",           "find_class",   lambda s: s.get("class_name", "").lower() == "parser"),
    ("insert function called greet","insert_function",lambda s: s.get("function_name") == "greet"),
    ("save snippet named my prog",  "save_snippet_named", lambda s: "my prog" in s.get("name", "")),
    ("set breakpoint at line 10",   "set_breakpoint",lambda s: s.get("line_number") == 10),
    ("watch variable counter",      "watch_variable",lambda s: s.get("variable") == "counter"),
    ("quiz me on variables",        "quiz_me",      lambda s: "variables" in s.get("topic", "")),
    ("run",                         "run",          lambda s: True),
    ("fix code",                    "fix",          lambda s: True),
    ("suggest next line",           "suggest_next", lambda s: True),
    ("repeat that",                 "repeat",       lambda s: True),
])
def test_intent_parser_direct(text, expected_intent, slot_check):
    result = parse_intent(text)
    assert result["intent"] == expected_intent, (
        f"Input {text!r}: expected {expected_intent!r}, got {result['intent']!r}"
    )
    assert slot_check(result["slots"]), (
        f"Slot check failed for {text!r}: {result['slots']}"
    )


def test_intent_parser_empty_string():
    result = parse_intent("")
    assert result["intent"] is None
    assert result["confidence"] == 0.0


def test_intent_parser_compound_numbers():
    """Spoken compound numbers like 'thirty seven' must parse correctly."""
    result = parse_intent("go to line thirty seven")
    assert result["intent"] == "goto_line"
    assert result["slots"]["line_number"] == 37


def test_intent_parser_no_false_goto_line():
    """Generic sentences mentioning 'line' must not trigger goto_line."""
    result = parse_intent("this is a single line program")
    assert result["intent"] != "goto_line"

# ===========================================================================
# 15. HINDI INTENT PARSING
# ===========================================================================

@pytest.mark.parametrize("hindi_text, expected_intent, slot_check", [
    # Numbers
    ("लाइन बीस पर जाओ",        "goto_line",    lambda s: s.get("line_number") == 20),
    ("लाइन पंद्रह पर जाओ",      "goto_line",    lambda s: s.get("line_number") == 15),
    ("लाइन पांच पढ़ो",          "read_line",    lambda s: s.get("line_number") == 5),
    ("line 10 पर जाओ",          "goto_line",    lambda s: s.get("line_number") == 10),

    # Execution
    ("चलाओ",                    "run",          lambda s: True),
    ("कोड चलाओ",                "run",          lambda s: True),
    ("रन करो",                  "run",          lambda s: True),

    # Analysis
    ("कोड का विश्लेषण करो",     "analyze",      lambda s: True),
    ("कोड समझाओ",               "analyze",      lambda s: True),

    # Fix
    ("कोड ठीक करो",             "fix",          lambda s: True),
    ("गलती ठीक करो",            "fix",          lambda s: True),
    ("सही करो",                 "fix",          lambda s: True),

    # Summarize
    ("सारांश दो",               "summarize",    lambda s: True),
    ("कोड का सारांश",           "summarize",    lambda s: True),

    # Suggest next
    ("अगली लाइन सुझाओ",         "suggest_next", lambda s: True),
    ("क्या लिखूं",              "suggest_next", lambda s: True),

    # Steps
    ("अगला कदम",                "next_step",    lambda s: True),
    ("पिछला कदम",               "previous_step",lambda s: True),
    ("आगे बढ़ो",                "next_step",    lambda s: True),
    ("पीछे जाओ",                "previous_step",lambda s: True),

    # Help
    ("मदद",                     "help",         lambda s: True),
    ("सहायता",                  "help",         lambda s: True),
    ("क्या कर सकते हो",         "help",         lambda s: True),

    # Clear
    ("एडिटर साफ करो",           "clear_editor", lambda s: True),
    ("कोड हटाओ",                "clear_editor", lambda s: True),
])
def test_hindi_intent_parsing(hindi_text, expected_intent, slot_check):
    """Hindi voice commands must parse to the correct intent."""
    result = parse_intent(hindi_text)
    assert result["intent"] == expected_intent, (
        f"Hindi input {hindi_text!r}: expected {expected_intent!r}, got {result['intent']!r}"
    )
    assert slot_check(result["slots"]), (
        f"Slot check failed for {hindi_text!r}: {result['slots']}"
    )


def test_hindi_number_parser_direct():
    """Hindi number words must convert to integers correctly."""
    from intent_parser import get_parser
    parser = get_parser()
    assert parser._word_to_number("बीस") == 20
    assert parser._word_to_number("पंद्रह") == 15
    assert parser._word_to_number("पचास") == 50
    assert parser._word_to_number("एक") == 1


def test_hindi_voice_command_via_http(client):
    """End-to-end: Hindi voice command through the /voice-command endpoint."""
    res = client.post("/voice-command", json={"text": "लाइन बीस पर जाओ"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["action"] == "goto_line"
    assert data["line"] == 20


def test_hindi_run_via_http(client):
    """End-to-end: Hindi run command."""
    res = client.post("/voice-command", json={"text": "कोड चलाओ"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["action"] == "run"

class TestPerSessionSandbox:

    def test_separate_sessions_get_different_workspaces(self):
        """Different session IDs must produce different sandbox instances."""
        from sandboxed_fs import get_sandbox
        sb1 = get_sandbox("test-session-aaa")
        sb2 = get_sandbox("test-session-bbb")
        assert sb1 is not sb2, "Different session IDs must return different sandbox instances"
        assert sb1.workspace_dir != sb2.workspace_dir, (
            "Different sessions must have different workspace directories"
        )

    def test_delete_in_one_session_does_not_affect_other(self):
        """Files written in one sandbox must not appear in another."""
        from sandboxed_fs import get_sandbox
        sb1 = get_sandbox("test-session-ccc")
        sb2 = get_sandbox("test-session-ddd")

        sb1.write("shared.txt", "A")
        sb2.write("shared.txt", "B")
        sb1.delete("shared.txt")

        result = sb2.read("shared.txt")
        assert result["success"] is True, "sb2's file should still exist after sb1 deleted its own copy"
        assert result["content"] == "B"

    def test_same_session_reads_own_files(self, client):
        w = client.post("/fs/write", json={"path": "mine.txt", "content": "hello"})
        assert w.get_json()["success"] is True
        r = client.post("/fs/read", json={"path": "mine.txt"})
        data = r.get_json()
        assert data["success"] is True
        assert data["content"] == "hello"

        
    def test_fs_info_reflects_only_own_files(self, tmp_snippets):
        os.environ["GEMINI_ENABLED"] = "0"
        with app.test_client() as c1, app.test_client() as c2:
            for i in range(3):
                c1.post("/fs/write", json={"path": f"file{i}.txt", "content": "x"})
            info1 = c1.get("/fs/info").get_json()
            info2 = c2.get("/fs/info").get_json()
            assert info1["total_files"] >= 3
            assert info2["total_files"] < info1["total_files"]
        os.environ["GEMINI_ENABLED"] = "1"


class TestCodeTempFile:

    @pytest.mark.timeout(15)
    def test_basic_execution_still_works(self, client):
        res = client.post("/run", json={"code": "print('file_path_ok')"})
        data = res.get_json()
        assert data["success"] is True
        assert "file_path_ok" in data["output"]

    @pytest.mark.timeout(20)
    def test_large_code_no_truncation(self, client):
        lines = [f"print('line_{i:04d}')" for i in range(200)]
        lines.append("print('END_SENTINEL')")
        res = client.post("/run", json={"code": "\n".join(lines)})
        data = res.get_json()
        assert data["success"] is True, f"Large code failed: {data.get('error')}"
        assert "END_SENTINEL" in data["output"]
        assert "line_0099" in data["output"]

    @pytest.mark.timeout(15)
    def test_trace_still_populated(self, client):
        res = client.post("/run", json={"code": "x = 42\nprint(x)"})
        data = res.get_json()
        assert data["success"] is True
        assert len(data.get("trace", [])) > 0

    @pytest.mark.timeout(15)
    def test_syntax_error_still_reported(self, client):
        res = client.post("/run", json={"code": "def foo(\n    pass"})
        data = res.get_json()
        assert data["success"] is False
        assert data.get("error")



class TestRunRateLimit:

    @pytest.mark.timeout(30)
    def test_rate_limit_blocks_after_threshold(self, client):
        limit = app_module.RUN_RATE_LIMIT
        results = [client.post("/run", json={"code": "print(1)"}).status_code
                   for _ in range(limit + 1)]
        assert 429 in results, f"Expected 429 after {limit} runs. Got: {results}"

    @pytest.mark.timeout(30)
    def test_rate_limit_allows_up_to_threshold(self, client):
        limit = app_module.RUN_RATE_LIMIT
        statuses = [client.post("/run", json={"code": "print(1)"}).status_code
                    for _ in range(limit)]
        assert all(s == 200 for s in statuses), f"Premature block: {statuses}"

    @pytest.mark.timeout(30)
    def test_rate_limit_is_per_session(self, tmp_snippets):
        os.environ["GEMINI_ENABLED"] = "0"
        limit = app_module.RUN_RATE_LIMIT
        with app.test_client() as c1, app.test_client() as c2:
            for _ in range(limit + 1):
                c1.post("/run", json={"code": "print(1)"})
            r2 = c2.post("/run", json={"code": "print(1)"})
            assert r2.status_code == 200, f"Session 2 wrongly rate-limited: {r2.status_code}"
        os.environ["GEMINI_ENABLED"] = "1"

    def test_rate_limit_constants_exist(self):
        assert hasattr(app_module, "RUN_RATE_LIMIT")
        assert hasattr(app_module, "RUN_RATE_WINDOW")
        assert app_module.RUN_RATE_LIMIT > 0
        assert app_module.RUN_RATE_WINDOW > 0

    @pytest.mark.timeout(10)
    def test_rate_limit_429_body(self, client):
        limit = app_module.RUN_RATE_LIMIT
        last = None
        for _ in range(limit + 1):
            last = client.post("/run", json={"code": "print(1)"})
        if last.status_code != 429:
            pytest.skip("Rate limit window may have reset; skipping body check")
        data = last.get_json()
        assert data["success"] is False
        assert "rate" in data["error"].lower() or "limit" in data["error"].lower()

class TestStructureParserFix:

    def setup_method(self):
        from structure_parser import CodeAnalyzer
        self.analyzer = CodeAnalyzer()

    def test_async_function_flagged(self):
        result = self.analyzer.analyze("async def fetch():\n    pass")
        fns = result["functions"]
        assert fns[0]["is_async"] is True

    def test_sync_function_not_flagged(self):
        result = self.analyzer.analyze("def greet():\n    pass")
        assert result["functions"][0]["is_async"] is False

    def test_mixed_async_and_sync(self):
        code = "def sync_fn():\n    pass\n\nasync def async_fn():\n    pass"
        fns = {f["name"]: f for f in self.analyzer.analyze(code)["functions"]}
        assert fns["sync_fn"]["is_async"] is False
        assert fns["async_fn"]["is_async"] is True

    def test_method_has_parent_class(self):
        code = "class Dog:\n    def bark(self):\n        pass"
        fns = {f["name"]: f for f in self.analyzer.analyze(code)["functions"]}
        assert fns["bark"]["parent_class"] == "Dog"

    def test_top_level_function_has_no_parent_class(self):
        result = self.analyzer.analyze("def standalone():\n    pass")
        assert result["functions"][0]["parent_class"] is None

    def test_method_and_standalone_together(self):
        code = "def top():\n    pass\n\nclass C:\n    def method(self):\n        pass"
        fns = {f["name"]: f for f in self.analyzer.analyze(code)["functions"]}
        assert fns["top"]["parent_class"] is None
        assert fns["method"]["parent_class"] == "C"

    def test_async_method_in_class(self):
        code = "class Fetcher:\n    async def get(self):\n        pass"
        fns = {f["name"]: f for f in self.analyzer.analyze(code)["functions"]}
        assert fns["get"]["is_async"] is True
        assert fns["get"]["parent_class"] == "Fetcher"

    def test_nested_function_not_in_top_list(self):
        code = ("class Outer:\n"
                "    def outer_method(self):\n"
                "        def inner():\n"
                "            pass\n")
        names = [f["name"] for f in self.analyzer.analyze(code)["functions"]]
        assert "inner" not in names
        assert "outer_method" in names

    def test_functions_sorted_by_line(self):
        code = "def b():\n    pass\n\ndef a():\n    pass\n\ndef c():\n    pass"
        lines = [f["line"] for f in self.analyzer.analyze(code)["functions"]]
        assert lines == sorted(lines)

    def test_structure_endpoint_includes_is_async(self, client):
        res = client.post("/structure", json={"code": "async def f():\n    pass"})
        fns = res.get_json()["structure"]["functions"]
        assert fns[0]["is_async"] is True

    def test_structure_endpoint_includes_parent_class(self, client):
        res = client.post("/structure", json={"code": "class Cat:\n    def meow(self):\n        pass"})
        fns = {f["name"]: f for f in res.get_json()["structure"]["functions"]}
        assert fns["meow"]["parent_class"] == "Cat"



class TestInputSandboxBackend:

    @pytest.mark.timeout(15)
    def test_input_call_fails(self, client):
        res = client.post("/run", json={"code": "x = input('enter: ')\nprint(x)"})
        assert res.get_json()["success"] is False

    @pytest.mark.timeout(15)
    def test_input_error_mentions_input(self, client):
        res = client.post("/run", json={"code": "name = input('name: ')"})
        data = res.get_json()
        combined = (data.get("error") or "") + (data.get("explanation") or "")
        assert "input" in combined.lower()

    @pytest.mark.timeout(15)
    def test_variable_named_my_input_not_blocked(self, client):
        res = client.post("/run", json={"code": "my_input = 42\nprint(my_input)"})
        data = res.get_json()
        assert data["success"] is True
        assert "42" in data["output"]

    @pytest.mark.timeout(15)
    def test_input_in_comment_not_blocked(self, client):
        res = client.post("/run", json={"code": "# input() disabled\nprint('ok')"})
        data = res.get_json()
        assert data["success"] is True

    @pytest.mark.timeout(15)
    def test_input_in_string_not_blocked(self, client):
        res = client.post("/run", json={"code": "msg = 'input() is disabled'\nprint(msg)"})
        data = res.get_json()
        assert data["success"] is True


class TestRegressionAfterFixes:

    @pytest.mark.timeout(15)
    def test_basic_print(self, client):
        data = client.post("/run", json={"code": "print('ok')"}).get_json()
        assert data["success"] is True and "ok" in data["output"]

    @pytest.mark.timeout(15)
    def test_os_import_blocked(self, client):
        assert client.post("/run", json={"code": "import os\nprint(os.getcwd())"}).get_json()["success"] is False

    @pytest.mark.timeout(15)
    def test_math_import_works(self, client):
        data = client.post("/run", json={"code": "import math\nprint(int(math.pi))"}).get_json()
        assert data["success"] is True and "3" in data["output"]

    def test_voice_goto_line(self, client):
        data = client.post("/voice-command", json={"text": "go to line ten"}).get_json()
        assert data["action"] == "goto_line" and data["line"] == 10

    def test_snippet_roundtrip(self, client):
        client.post("/snippets", json={"name": "reg", "code": "print(1)"})
        assert any(s["name"] == "reg" for s in client.get("/snippets").get_json()["snippets"])

    def test_syntax_check(self, client):
        assert client.post("/check-syntax", json={"code": "x = 1"}).get_json()["has_errors"] is False

    @pytest.mark.timeout(15)
    def test_trace_endpoint(self, client):
        client.post("/run", json={"code": "x = 1"})
        data = client.get("/execution-trace").get_json()
        assert "trace" in data and "current_index" in data

class TestSnippetSessionIsolation:
    def test_snippets_are_per_session(self, tmp_snippets):
        """Two sessions must not see each other's snippets."""
        os.environ["GEMINI_ENABLED"] = "0"
        try:
            c1 = app.test_client()
            c2 = app.test_client()

            c1.post("/snippets", json={"name": "alice_only", "code": "print('alice')"})
            c2.post("/snippets", json={"name": "bob_only",   "code": "print('bob')"})

            alice_list = c1.get("/snippets").get_json()["snippets"]
            bob_list   = c2.get("/snippets").get_json()["snippets"]

            alice_names = [s["name"] for s in alice_list]
            bob_names   = [s["name"] for s in bob_list]

            assert "alice_only" in alice_names
            assert "alice_only" not in bob_names
            assert "bob_only" in bob_names
            assert "bob_only" not in alice_names
        finally:
            os.environ["GEMINI_ENABLED"] = "1"


# ===========================================================================
# 16. PRE-FLIGHT INPUTS (Mechanism A)
# ===========================================================================

class TestPreflightInputs:

    @pytest.mark.timeout(15)
    def test_input_with_preflight_succeeds(self, client):
        code = "name = input('Your name: ')\nprint('Hello,', name)"
        res = client.post("/run", json={"code": code, "inputs": ["Alice"]})
        data = res.get_json()
        assert data["success"] is True, f"Pre-flight input failed: {data.get('error')}"
        assert "Alice" in data["output"]
        assert "Hello" in data["output"]

    @pytest.mark.timeout(15)
    def test_multiple_preflight_inputs(self, client):
        code = "a = input('a: ')\nb = input('b: ')\nprint(a + ' and ' + b)"
        res = client.post("/run", json={"code": code, "inputs": ["foo", "bar"]})
        data = res.get_json()
        assert data["success"] is True
        assert "foo and bar" in data["output"]

    @pytest.mark.timeout(15)
    def test_too_few_inputs_friendly_error(self, client):
        code = "a = input('a: ')\nb = input('b: ')\nprint(a, b)"
        res = client.post("/run", json={"code": code, "inputs": ["only_one"]})
        data = res.get_json()
        assert data["success"] is False
        combined = (data.get("error") or "") + (data.get("explanation") or "")
        assert "input" in combined.lower()

    @pytest.mark.timeout(15)
    def test_magic_comment_inputs(self, client):
        code = "# inputs: hello, world\na = input()\nb = input()\nprint(a, b)"
        res = client.post("/run", json={"code": code})
        data = res.get_json()
        assert data["success"] is True
        assert "hello" in data["output"] and "world" in data["output"]

    @pytest.mark.timeout(15)
    def test_body_inputs_override_magic_comment(self, client):
        code = "# inputs: from_magic\nname = input()\nprint(name)"
        res = client.post("/run", json={"code": code, "inputs": ["from_body"]})
        data = res.get_json()
        assert data["success"] is True
        assert "from_body" in data["output"]
        assert "from_magic" not in data["output"]

    @pytest.mark.timeout(15)
    def test_inputs_hint_when_input_used_without_inputs(self, client):
        code = "x = input('?')\nprint(x)"
        res = client.post("/run", json={"code": code})
        data = res.get_json()
        assert data.get("inputs_hint")
        assert "input" in data["inputs_hint"].lower()


class TestVoiceSetInputs:

    def test_set_inputs_basic(self, client):
        res = client.post("/voice-command", json={"text": "set inputs to Alice and 17"})
        data = res.get_json()
        assert data["action"] == "set_inputs"
        assert "Alice" in data["values"]
        assert "17" in data["values"]

    def test_set_inputs_with_commas(self, client):
        res = client.post("/voice-command", json={"text": "set inputs to foo, bar, baz"})
        data = res.get_json()
        assert data["action"] == "set_inputs"
        assert data["values"] == ["foo", "bar", "baz"]

    def test_clear_inputs_command(self, client):
        res = client.post("/voice-command", json={"text": "clear inputs"})
        data = res.get_json()
        assert data["action"] == "clear_inputs"

    def test_live_input_mode_command(self, client):
        res = client.post("/voice-command", json={"text": "live input mode"})
        data = res.get_json()
        assert data["action"] == "live_input_mode"


# ===========================================================================
# 17. VOICE MACROS
# ===========================================================================

class TestVoiceMacros:

    def test_save_macro_via_command(self, client):
        res = client.post("/voice-command", json={"text": "remember this as my pattern"})
        data = res.get_json()
        assert data["action"] == "save_macro"
        assert data["name"] == "my pattern"

    def test_use_macro_via_command(self, client):
        res = client.post("/voice-command", json={"text": "use macro my pattern"})
        data = res.get_json()
        assert data["action"] == "use_macro"
        assert data["name"] == "my pattern"

    def test_save_and_load_macro_endpoint(self, client):
        save = client.post("/macros", json={"name": "greeting", "code": "print('hi')"})
        assert save.get_json()["success"] is True

        get = client.get("/macros/get/greeting")
        data = get.get_json()
        assert data["success"] is True
        assert "print" in data["code"]

    def test_macro_invalid_name_rejected(self, client):
        res = client.post("/macros", json={"name": "bad/name", "code": "x"})
        assert res.status_code == 400

    def test_macro_too_large_rejected(self, client):
        res = client.post("/macros", json={"name": "big", "code": "x = 1\n" * 20_000})
        assert res.status_code == 413

    def test_list_macros_endpoint(self, client):
        client.post("/macros", json={"name": "alpha", "code": "print(1)"})
        res = client.get("/macros")
        data = res.get_json()
        assert data["success"] is True
        assert "alpha" in data["names"]


# ===========================================================================
# 18. OUTPUT BOOKMARKS
# ===========================================================================

class TestOutputBookmarks:

    def test_save_bookmark(self, client):
        res = client.post("/bookmarks", json={"label": "test_mark", "position": 100})
        data = res.get_json()
        assert data["success"] is True

    def test_list_bookmarks(self, client):
        client.post("/bookmarks", json={"label": "first", "position": 0})
        client.post("/bookmarks", json={"label": "second", "position": 50})
        res = client.get("/bookmarks")
        data = res.get_json()
        assert len(data["bookmarks"]) == 2

    def test_clear_bookmarks(self, client):
        client.post("/bookmarks", json={"label": "x", "position": 0})
        client.delete("/bookmarks")
        res = client.get("/bookmarks")
        assert res.get_json()["bookmarks"] == []

    def test_read_from_bookmark(self, client):
        client.post("/bookmarks", json={"label": "mid", "position": 6})
        res = client.post("/bookmarks/read", json={"label": "mid", "output": "abcdef_END"})
        data = res.get_json()
        assert data["success"] is True
        assert data["slice"] == "_END"


# ===========================================================================
# 19. BREADCRUMBS
# ===========================================================================

class TestBreadcrumbs:

    def test_top_level(self, client):
        res = client.post("/breadcrumbs", json={"code": "x = 1", "line": 1})
        data = res.get_json()
        assert data["success"] is True
        assert "top level" in data["breadcrumb"].lower()

    def test_inside_function(self, client):
        code = "def hello():\n    x = 1\n    print(x)"
        res = client.post("/breadcrumbs", json={"code": code, "line": 3})
        data = res.get_json()
        assert data["success"] is True
        assert "function" in data["breadcrumb"].lower()
        assert "hello" in data["breadcrumb"]

    def test_inside_loop_in_function(self, client):
        code = "def calc():\n    for i in range(5):\n        print(i)"
        res = client.post("/breadcrumbs", json={"code": code, "line": 3})
        data = res.get_json()
        assert data["success"] is True
        assert "calc" in data["breadcrumb"]
        assert "for loop" in data["breadcrumb"].lower()


# ===========================================================================
# 20. OUTPUT DIFF NARRATION
# ===========================================================================

class TestOutputDiff:

    @pytest.mark.timeout(15)
    def test_first_run_no_diff(self, client):
        res = client.post("/run", json={"code": "print('hi')"})
        data = res.get_json()
        assert data["success"] is True
        # First run: diff present but identical=False with empty changed_lines
        assert "diff" in data

    @pytest.mark.timeout(15)
    def test_second_identical_run_marked_identical(self, client):
        client.post("/run", json={"code": "print('same')"})
        res = client.post("/run", json={"code": "print('same')"})
        data = res.get_json()
        assert data["success"] is True
        assert data["diff"]["identical"] is True

    @pytest.mark.timeout(15)
    def test_changed_output_diff_detected(self, client):
        client.post("/run", json={"code": "print(1)"})
        res = client.post("/run", json={"code": "print(2)"})
        data = res.get_json()
        assert data["success"] is True
        assert data["diff"]["identical"] is False
        assert data["diff"]["total_changes"] >= 1


# ===========================================================================
# 21. BEGINNER ERROR EXPLANATION
# ===========================================================================

class TestBeginnerErrorExplanation:

    def test_endpoint_exists(self, client):
        res = client.post("/explain-error-beginner", json={
            "code": "x = 1",
            "error": "NameError: name 'y' is not defined",
            "language": "en"
        })
        # AI is disabled in tests so we get a "service disabled" response
        # but the endpoint should respond 200, not crash.
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        assert "explanation" in data

    def test_endpoint_rejects_empty_error(self, client):
        res = client.post("/explain-error-beginner", json={
            "code": "x = 1",
            "error": "",
            "language": "en"
        })
        assert res.status_code == 400


# ===========================================================================
# 22. INTENT PARSER — NEW INTENTS
# ===========================================================================

class TestNewIntents:

    @pytest.mark.parametrize("text, intent, slot_check", [
        ("set inputs to alice and seventeen",
            "set_inputs", lambda s: "alice" in [v.lower() for v in s.get("values", [])]),
        ("set inputs to foo, bar, baz",
            "set_inputs", lambda s: s.get("values") == ["foo", "bar", "baz"]),
        ("clear inputs",          "clear_inputs", lambda s: True),
        ("list inputs",           "list_inputs",  lambda s: True),
        ("live input mode",       "live_input_mode", lambda s: True),
        ("preflight input mode",  "preflight_input_mode", lambda s: True),
        ("remember this as quick sort", "save_macro", lambda s: s.get("name") == "quick sort"),
        ("use macro quick sort",  "use_macro", lambda s: s.get("name") == "quick sort"),
        ("list macros",           "list_macros", lambda s: True),
        ("bookmark this",         "bookmark_output", lambda s: True),
        ("bookmark this as totals", "bookmark_output", lambda s: s.get("label") == "totals"),
        ("read from bookmark totals", "read_bookmark", lambda s: s.get("label") == "totals"),
        ("list bookmarks",        "list_bookmarks", lambda s: True),
        ("where am i",            "where_am_i", lambda s: True),
        ("explain like i'm five", "explain_simply", lambda s: True),
        ("what's different",      "narrate_diff", lambda s: True),
    ])
    def test_intent(self, text, intent, slot_check):
        result = parse_intent(text)
        assert result["intent"] == intent, (
            f"Input {text!r}: expected {intent!r}, got {result['intent']!r}"
        )
        assert slot_check(result["slots"]), (
            f"Slot check failed for {text!r}: {result['slots']}"
        )