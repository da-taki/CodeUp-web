"""Tests for the proof-based teaching loop: runtime teacher, DOM/JS debugger,
selector explainer, readiness score, guided build track, and pilot report.

Run → observe → explain by facts → help fix → replay. Deterministic, no AI key.
"""

import io
import zipfile

import pytest

from codeup.services.guided_build import guided_recap, guided_steps, validate_guided_step
from codeup.services.project_explainer import build_pilot_report
from codeup.services.selector_explainer import build_selector_explainer
from codeup.services.site_generator import generate_site_files
from codeup.services.website_accessibility_lab import build_readiness_report
from codeup.services.website_debugger import build_debug_teacher
from codeup.services.website_runtime_teacher import build_runtime_teacher


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    monkeypatch.setenv("AI_CLOUD_ENABLED", "0")
    import app as app_module
    import codeup.config as config_module

    monkeypatch.setattr(config_module, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


ROBOTICS = generate_site_files("make a website for my school robotics club")
QUIZ = generate_site_files("make a quiz app about Python basics")

# A small site with a deliberate id typo: JS asks for #joinBtn, HTML has #joinButton.
TYPO_JS = "var b = document.getElementById('joinBtn'); b.addEventListener('click', function(){});"
TYPO_HTML = "<main><h1>Robotics Club</h1><button id='joinButton'>Join Team</button></main>"


def _payload(files, **extra):
    body = {
        "name": "Demo",
        "project_type": files["project_type"],
        "html": files["html"],
        "css": files["css"],
        "js": files["js"],
    }
    body.update(extra)
    return body


# --------------------------------------------------------------------------- #
# Command routing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("command", "action"),
    [
        # Runtime teacher (new phrases). "run website" stays run_summary by design.
        ("run website", "run_summary"),
        ("what happens when this runs", "runtime_teacher"),
        ("runtime teacher", "runtime_teacher"),
        ("teach me how this website runs", "runtime_teacher"),
        # Debug teacher.
        ("debug website", "debug_website"),
        ("debug this like a teacher", "debug_website"),
        ("why is my button not working", "debug_website"),
        ("check javascript connections", "debug_website"),
        ("explain errors", "debug_website"),
        ("fix website error", "debug_fix"),
        # Selector explainer.
        ("what CSS affects this button", "selector_explainer"),
        ("explain CSS for hero", "selector_explainer"),
        ("which CSS affects the contact form", "selector_explainer"),
        ("find unused CSS", "selector_explainer"),
        ("which HTML uses this class", "selector_explainer"),
        # Readiness.
        ("is this ready to share", "readiness_score"),
        ("can I export this", "readiness_score"),
        ("teacher check", "readiness_score"),
        ("NAB readiness check", "readiness_score"),
        # Pilot report.
        ("make pilot report", "pilot_report"),
        ("make trainer report", "pilot_report"),
        ("summarize this session", "pilot_report"),
        ("what did the student learn", "pilot_report"),
        # Guided build.
        ("start web tutorial", "guided_build_start"),
        ("build my first website", "guided_build_start"),
        # Existing behaviour must be preserved.
        ("explain CSS", "file_explanation"),
        ("trainer notes", "trainer_notes"),
        ("what did I learn today", "student_recap"),
        ("start HTML tutorial", "tutorial_start"),
        ("check accessibility", "audit_site"),
        ("make a website for my robotics club", "build_site"),
    ],
)
def test_proof_loop_commands_route(client, command, action):
    routed = client.post("/voice-command", json={"text": command}).get_json()
    assert routed["action"] == action, command


def test_selector_explainer_query_slot(client):
    routed = client.post("/voice-command", json={"text": "what CSS affects the join button"}).get_json()
    assert routed["slots"]["query"]


# --------------------------------------------------------------------------- #
# Runtime teacher
# --------------------------------------------------------------------------- #
def test_runtime_teacher_facts_shape():
    result = build_runtime_teacher(
        ROBOTICS["html"], ROBOTICS["css"], ROBOTICS["js"], project_type=ROBOTICS["project_type"]
    )
    facts = result["facts"]
    assert set(facts) == {"title", "headings", "controls", "queries", "listeners", "mismatches"}
    assert facts["title"]
    assert isinstance(facts["headings"], list) and facts["headings"]
    assert "WEBSITE RUNTIME TEACHER" in result["text"]
    # It is honest about being a static check.
    assert "did not click" in result["text"].lower()


def test_runtime_teacher_reports_matched_selector():
    html = "<main><h1>Robotics Club Home Page</h1><button id='joinButton'>Join the Team Today</button></main>"
    js = "document.getElementById('joinButton').addEventListener('click', function(){});"
    result = build_runtime_teacher(html, "", js)
    assert not result["facts"]["mismatches"]
    assert "#joinButton" in result["text"]
    assert "matches an element" in result["text"]


def test_runtime_teacher_flags_selector_mismatch():
    result = build_runtime_teacher(TYPO_HTML, "", TYPO_JS)
    mismatches = result["facts"]["mismatches"]
    assert mismatches
    assert mismatches[0]["selector"] == "#joinBtn"
    assert mismatches[0]["did_you_mean"] == "#joinButton"
    assert "#joinBtn" in result["text"]
    assert "no HTML element matches" in result["text"]


def test_runtime_teacher_without_website_is_honest():
    result = build_runtime_teacher("", "", "")
    assert "make a website" in result["text"].lower()
    assert result["facts"]["headings"] == []


# --------------------------------------------------------------------------- #
# DOM / JS mismatch debugger
# --------------------------------------------------------------------------- #
def _issue_schema_ok(issue):
    return {"severity", "file", "line", "problem", "why_it_matters", "suggested_fix", "spoken_summary"} <= set(issue)


def test_debug_teacher_issue_schema():
    result = build_debug_teacher(TYPO_HTML, "", TYPO_JS)
    assert result["issues"]
    assert all(_issue_schema_ok(issue) for issue in result["issues"])
    assert all(issue["severity"] in {"high", "medium", "low"} for issue in result["issues"])


def test_debug_teacher_detects_typo_selector():
    result = build_debug_teacher(TYPO_HTML, "", TYPO_JS)
    top = result["issues"][0]
    assert top["severity"] == "high"
    assert top["file"] == "script.js"
    assert "#joinButton" in top["suggested_fix"]
    assert "#joinBtn" in top["spoken_summary"]


def test_debug_teacher_detects_missing_class_query():
    js = "document.querySelector('.missing').textContent = 'x';"
    result = build_debug_teacher("<main><h1>Hi</h1><div class='box'></div></main>", "", js)
    high = [i for i in result["issues"] if i["severity"] == "high"]
    assert any(i["file"] == "script.js" and ".missing" in i["problem"] for i in high)


def test_debug_teacher_detects_duplicate_id():
    html = '<main><h1 id="t">A</h1><h2 id="t">B</h2></main>'
    result = build_debug_teacher(html, "", "")
    assert any(i["severity"] == "high" and "used 2 times" in i["problem"] for i in result["issues"])


def test_debug_teacher_detects_unnamed_button():
    result = build_debug_teacher("<main><h1>Hi</h1><button></button></main>", "", "")
    assert any("no readable label" in i["problem"] for i in result["issues"])


def test_debug_teacher_detects_css_matching_nothing():
    result = build_debug_teacher("<main><h1>Hi</h1></main>", ".ghost { color: red; }", "")
    css_issues = [i for i in result["issues"] if i["file"] == "style.css"]
    assert css_issues and ".ghost" in css_issues[0]["problem"]


def test_debug_teacher_detects_button_with_no_type_in_form():
    html = "<main><form><button>Send</button></form></main>"
    result = build_debug_teacher(html, "", "")
    assert any("no type attribute" in i["problem"] for i in result["issues"])


def test_debug_teacher_detects_form_without_submit_listener():
    html = "<main><form><label>Name<input id='n'></label></form></main>"
    js = "console.log('hi');"
    result = build_debug_teacher(html, "", js)
    assert any("no submit listener" in i["problem"] for i in result["issues"])


def test_debug_teacher_honest_when_clean():
    result = build_debug_teacher(ROBOTICS["html"], ROBOTICS["css"], ROBOTICS["js"])
    assert result["issues"] == []
    assert "did not find a broken connection" in result["text"]


def test_debug_teacher_does_not_false_flag_single_char_var_listener():
    # b.addEventListener('click', ...) — the parser misses single-char vars, but the
    # debugger must not claim "no click listener" because the JS clearly has one.
    html = "<main><button id='joinButton'>Go</button></main>"
    js = "var b = document.getElementById('joinButton'); b.addEventListener('click', function(){});"
    result = build_debug_teacher(html, "", js)
    assert not any("no click listener" in i["problem"] for i in result["issues"])


def test_debug_teacher_handles_missing_html_and_empty_js():
    assert build_debug_teacher("", "", "")["issues"] == []
    # JS that queries something with no HTML at all -> high mismatch.
    result = build_debug_teacher("", "", "document.getElementById('x').focus();")
    assert any(i["severity"] == "high" for i in result["issues"])


# --------------------------------------------------------------------------- #
# Selector explainer
# --------------------------------------------------------------------------- #
def test_selector_explainer_maps_css_to_button():
    html = "<main><h1>Robotics</h1><button class='primary-button'>Join Team</button></main>"
    css = ".primary-button { background: navy; color: white; padding: 8px; border-radius: 6px; }"
    result = build_selector_explainer(html, css, "", "what CSS affects the join button")
    assert result["matched_elements"]
    assert any(rule["selector"] == ".primary-button" for rule in result["css_selectors"])
    assert ".primary-button" in result["text"]
    assert "CSS line 1" in result["text"]


def test_selector_explainer_finds_unused_css():
    result = build_selector_explainer(
        "<main><h1>Hi</h1></main>", ".ghost{color:red} h1{color:blue}", "", "find unused CSS"
    )
    assert result["unused"] is True
    selectors = [rule["selector"] for rule in result["css_selectors"]]
    assert ".ghost" in selectors
    assert "h1" not in selectors  # h1 matches, so it is not unused


def test_selector_explainer_which_html_uses_class():
    result = build_selector_explainer(
        "<main><p class='note'>x</p></main>", ".note{color:red}", "", "which HTML uses note"
    )
    assert result["matched_elements"]
    assert result["matched_elements"][0]["tag"] == "p"


def test_selector_explainer_no_match_is_graceful():
    result = build_selector_explainer("<main><h1>Hi</h1></main>", "", "", "what CSS affects the spaceship")
    assert result["matched_elements"] == []
    assert "could not find" in result["text"].lower()


# --------------------------------------------------------------------------- #
# Readiness score
# --------------------------------------------------------------------------- #
def test_readiness_report_shape_and_level():
    result = build_readiness_report(
        ROBOTICS["html"], ROBOTICS["css"], ROBOTICS["js"], project_type=ROBOTICS["project_type"]
    )
    assert set(result) >= {"score", "level", "text", "blockers", "suggestions"}
    assert 0 <= result["score"] <= 100
    assert result["level"] in {"ready", "almost ready", "needs work"}
    assert "Readiness score:" in result["text"]


def test_readiness_report_blocks_on_unlabeled_form_and_js_mismatch():
    html = "<main><h1>Contact</h1><form><input type='text'></form></main>"
    js = "document.getElementById('sendBtn').addEventListener('click', function(){});"
    result = build_readiness_report(html, "", js)
    blockers_text = " ".join(result["blockers"]).lower()
    assert "label" in blockers_text  # form input without a label
    assert "#sendbtn" in blockers_text or "sendbtn" in blockers_text  # broken JS selector
    assert result["level"] in {"needs work", "almost ready"}


def test_readiness_report_clean_site_has_no_blockers_text():
    result = build_readiness_report(ROBOTICS["html"], ROBOTICS["css"], ROBOTICS["js"])
    if not result["blockers"]:
        assert "did not find any blockers" in result["text"].lower()


# --------------------------------------------------------------------------- #
# Guided build track
# --------------------------------------------------------------------------- #
def test_guided_steps_are_complete():
    steps = guided_steps()
    assert len(steps) == 12
    for step in steps:
        assert step["id"] and step["title"] and step["say"] and step["command"] and step["hint"] and step["success"]
        assert "check" not in step  # callables are not serialized


def test_guided_step_validation_pass_and_fail():
    ok = validate_guided_step("button", "<main><button>Join</button></main>", "", "")
    assert ok["valid"] is True
    assert "Success" in ok["message"]
    bad = validate_guided_step("button", "<main><p>no button</p></main>", "", "")
    assert bad["valid"] is False
    assert bad["hint"]


def test_guided_step_validation_js_behavior():
    html = "<main><button id='go'>Go</button></main>"
    good = validate_guided_step(
        "js_behavior", html, "", "document.getElementById('go').addEventListener('click', () => {});"
    )
    assert good["valid"] is True
    bad = validate_guided_step("js_behavior", html, "", "")
    assert bad["valid"] is False


def test_guided_unknown_step():
    result = validate_guided_step("does_not_exist", "<main></main>", "", "")
    assert result["valid"] is False


def test_guided_recap_counts_progress():
    html = "<title>Hi</title><main><h1>Hi</h1><p>Text</p></main>"
    recap = guided_recap(html, "", "")
    assert recap["total"] == 12
    assert recap["completed"] >= 3  # title, heading, paragraph
    assert "GUIDED BUILD RECAP" in recap["text"]


def test_guided_endpoints(client):
    steps = client.get("/guided-build/steps").get_json()
    assert steps["success"] and len(steps["steps"]) == 12
    validate = client.post(
        "/guided-build/validate",
        json={"step": "heading", "html": "<main><h1>Welcome</h1></main>", "css": "", "js": ""},
    ).get_json()
    assert validate["success"] and validate["valid"] is True


# --------------------------------------------------------------------------- #
# Pilot report
# --------------------------------------------------------------------------- #
def test_pilot_report_includes_required_sections():
    text = build_pilot_report(
        ROBOTICS["html"],
        ROBOTICS["css"],
        ROBOTICS["js"],
        name="Robotics",
        project_type=ROBOTICS["project_type"],
        commands=["make a website for my robotics club", "run website", "fix accessibility issues"],
    )
    for marker in (
        "PILOT SESSION REPORT",
        "Files created:",
        "Accessibility score:",
        "Readiness score:",
        "Commands used:",
        "Mistakes found:",
        "Concepts learned:",
        "Suggested next lesson:",
        "Trainer notes:",
    ):
        assert marker in text, marker
    assert "fix accessibility issues" in text


def test_pilot_report_without_commands_still_renders():
    text = build_pilot_report(ROBOTICS["html"], ROBOTICS["css"], ROBOTICS["js"], project_type=ROBOTICS["project_type"])
    assert "PILOT SESSION REPORT" in text
    assert "command history was not recorded" in text


def test_pilot_report_route(client):
    data = client.post("/pilot-report", json=_payload(ROBOTICS, commands=["run website", "debug website"])).get_json()
    assert data["success"] is True
    assert "PILOT SESSION REPORT" in data["text"]


# --------------------------------------------------------------------------- #
# Export integration
# --------------------------------------------------------------------------- #
def _export(client, **extra):
    body = {
        "name": "Robotics",
        "project_type": ROBOTICS["project_type"],
        "files": {"index.html": ROBOTICS["html"], "style.css": ROBOTICS["css"], "script.js": ROBOTICS["js"]},
    }
    body.update(extra)
    return client.post("/export-site.zip", json=body)


def test_export_includes_pilot_report_when_session_data_exists(client):
    response = _export(client, commands=["make a website", "run website", "debug website"])
    assert response.status_code == 200
    names = set(zipfile.ZipFile(io.BytesIO(response.data)).namelist())
    assert "PILOT_REPORT.txt" in names


def test_export_omits_pilot_report_without_session_data(client):
    response = _export(client)
    names = set(zipfile.ZipFile(io.BytesIO(response.data)).namelist())
    assert "PILOT_REPORT.txt" not in names


def test_export_contains_all_demo_artifacts_and_real_pilot_report(client):
    response = _export(
        client,
        audit={"score": 90, "issues": [], "suggestions": []},
        commands=["make a website for my robotics club", "debug website", "readiness score"],
    )
    assert response.status_code == 200
    bundle = zipfile.ZipFile(io.BytesIO(response.data))
    names = set(bundle.namelist())
    assert {
        "index.html",
        "style.css",
        "script.js",
        "README.txt",
        "CODE_MAP.txt",
        "STEP_NARRATION.txt",
        "ACCESSIBILITY_REPORT.txt",
        "PILOT_REPORT.txt",
    } <= names
    pilot = bundle.read("PILOT_REPORT.txt").decode("utf-8")
    # Not empty and not the generic "no website yet" placeholder.
    assert len(pilot) > 200
    assert "no website yet" not in pilot.lower()
    assert "Readiness score:" in pilot
    assert "debug website" in pilot  # a real recorded command


# --------------------------------------------------------------------------- #
# Endpoints are read-only (never return code/files to mutate the editor)
# --------------------------------------------------------------------------- #
def test_new_endpoints_do_not_mutate_files(client):
    for endpoint in (
        "/website-runtime-teacher",
        "/website-debug-teacher",
        "/selector-explainer",
        "/accessibility-readiness-score",
        "/pilot-report",
    ):
        data = client.post(endpoint, json=_payload(ROBOTICS)).get_json()
        assert data["success"] is True
        assert "files" not in data and "html" not in data and "code" not in data


def test_runtime_and_debug_endpoints_return_expected_keys(client):
    rt = client.post("/website-runtime-teacher", json=_payload(ROBOTICS)).get_json()
    assert "text" in rt and "facts" in rt
    dt = client.post("/website-debug-teacher", json=_payload(ROBOTICS)).get_json()
    assert "text" in dt and "issues" in dt
    rr = client.post("/accessibility-readiness-score", json=_payload(ROBOTICS)).get_json()
    assert {"score", "level", "blockers", "suggestions", "text"} <= set(rr)


# --------------------------------------------------------------------------- #
# Demo flow (end to end through the deterministic services, no AI key)
# --------------------------------------------------------------------------- #
def test_demo_flow(client):
    files = generate_site_files("make a website for my school robotics club")
    payload = _payload(files)

    # 2. run website
    assert client.post("/website-runtime-teacher", json=payload).get_json()["success"]
    # 3. what CSS affects the join button
    se = client.post("/selector-explainer", json=_payload(files, query="what CSS affects the join button")).get_json()
    assert se["success"]
    # 4. debug website
    assert client.post("/website-debug-teacher", json=payload).get_json()["success"]
    # 5. check accessibility
    assert client.post("/html-audit", json={"html": files["html"]}).get_json()["success"]
    # 6. is this ready to share
    rr = client.post("/accessibility-readiness-score", json=payload).get_json()
    assert rr["success"] and 0 <= rr["score"] <= 100
    # 9. make pilot report
    pr = client.post("/pilot-report", json=_payload(files, commands=["make a website", "run website"])).get_json()
    assert pr["success"] and "PILOT SESSION REPORT" in pr["text"]
    # 10. export website (with session data -> includes the pilot report)
    response = client.post(
        "/export-site.zip",
        json={
            "name": "Robotics",
            "project_type": files["project_type"],
            "files": {"index.html": files["html"], "style.css": files["css"], "script.js": files["js"]},
            "commands": ["make a website", "run website", "debug website"],
        },
    )
    assert response.status_code == 200
    names = set(zipfile.ZipFile(io.BytesIO(response.data)).namelist())
    assert {"index.html", "PILOT_REPORT.txt", "READINESS_SCORE.txt", "RUN_SUMMARY.txt"} <= names


# --------------------------------------------------------------------------- #
# Hardening: empty-project behaviour (no crash, no confusing "success")
# --------------------------------------------------------------------------- #
def test_empty_project_runtime_is_clear():
    result = build_runtime_teacher("", "", "")
    assert "make a website" in result["text"].lower()
    assert result["speech"]
    assert result["facts"]["headings"] == []


def test_empty_project_debug_says_build_first():
    result = build_debug_teacher("", "", "")
    assert result["issues"] == []
    assert "nothing to debug" in result["text"].lower()
    assert "build or load a website first" in result["speech"].lower()


def test_empty_project_readiness_is_not_ready():
    result = build_readiness_report("", "", "")
    assert result["score"] == 0
    assert result["level"] == "needs work"
    assert result["blockers"] == []
    assert "no website yet" in result["text"].lower()
    assert "ready to share" not in result["text"].lower()


def test_empty_project_pilot_is_short_and_clear():
    text = build_pilot_report("", "", "")
    assert "no website yet" in text.lower()
    assert "Accessibility score" not in text  # no generic filled-in report


def test_empty_project_endpoints_do_not_crash(client):
    blank = {"html": "", "css": "", "js": ""}
    for endpoint in (
        "/website-runtime-teacher",
        "/website-debug-teacher",
        "/accessibility-readiness-score",
        "/pilot-report",
    ):
        data = client.post(endpoint, json=blank).get_json()
        assert data["success"] is True


def test_css_only_project_is_not_treated_as_blank():
    # A project with only CSS is not blank; the debugger should still inspect it.
    result = build_debug_teacher("", ".ghost{color:red}", "")
    assert "nothing to debug" not in result["text"].lower()


# --------------------------------------------------------------------------- #
# Hardening: short spoken summaries (speech field)
# --------------------------------------------------------------------------- #
def _short(text, limit=320):
    return bool(text) and len(text) <= limit


def test_endpoints_return_short_speech(client):
    payload = _payload(ROBOTICS)
    rt = client.post("/website-runtime-teacher", json=payload).get_json()
    dt = client.post("/website-debug-teacher", json=payload).get_json()
    rr = client.post("/accessibility-readiness-score", json=payload).get_json()
    se = client.post("/selector-explainer", json=_payload(ROBOTICS, query="what CSS affects the button")).get_json()
    pr = client.post("/pilot-report", json=_payload(ROBOTICS, commands=["run website"])).get_json()
    for label, data in (("runtime", rt), ("debug", dt), ("readiness", rr), ("selector", se), ("pilot", pr)):
        assert data.get("speech"), label
        # The spoken summary must be much shorter than the full on-screen report.
        assert _short(data["speech"]), f"{label} speech too long: {len(data['speech'])}"
        assert len(data["speech"]) < len(data["text"]), label


def test_broken_js_speech_is_concise_and_names_fix():
    html = "<main><h1>Robotics Club Home</h1><button id='joinButton'>Join Team</button></main>"
    js = 'const btn = document.getElementById("joinBtn"); btn.addEventListener("click", () => {});'
    dt = build_debug_teacher(html, "", js)
    assert _short(dt["speech"])
    assert "#joinButton" in dt["speech"]


def test_guided_recap_has_short_speech():
    recap = guided_recap("<title>Hi</title><main><h1>Hi</h1></main>", "", "")
    assert recap["speech"] and _short(recap["speech"], 200)


def test_no_speech_does_not_contain_code_blocks(client):
    # Spoken summaries must not dump raw code/markup.
    payload = _payload(ROBOTICS)
    for endpoint in ("/website-runtime-teacher", "/website-debug-teacher", "/accessibility-readiness-score"):
        speech = client.post(endpoint, json=payload).get_json().get("speech", "")
        assert "<" not in speech and "{" not in speech and "```" not in speech


# --------------------------------------------------------------------------- #
# Hardening: readiness demo (#4) never says "ready" with real blockers
# --------------------------------------------------------------------------- #
def test_readiness_demo_lists_blockers_and_is_not_ready():
    html = "<main><h1>Contact</h1><form><input type='text'></form><button></button></main>"
    css = "body{color:#bbb;background:#ccc}"
    js = 'document.getElementById("sendBtn").addEventListener("click", ()=>{});'
    result = build_readiness_report(html, css, js)
    assert result["level"] != "ready"
    assert result["blockers"]
    blockers_text = " ".join(result["blockers"]).lower()
    assert "label" in blockers_text  # unlabeled form input
    assert "#sendbtn" in blockers_text or "sendbtn" in blockers_text  # JS mismatch
