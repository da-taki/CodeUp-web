"""Tests for the README/docs consolidation and the ported CodeUp learning features.

Covers command routing for the new features, fuzzy command repair, export
additions, safety (no code generation / no file mutation), and a few UI checks.
"""

import io
import zipfile
from pathlib import Path

import pytest

from codeup.services.intent_router import repair_command
from codeup.services.project_explainer import (
    build_screen_reader_summary,
    build_student_recap,
    build_trainer_notes,
)
from codeup.services.site_generator import generate_site_files

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
SECURITY = REPO_ROOT / "SECURITY.md"
FRONTEND_JS = REPO_ROOT / "static" / "codeup-html.js"
INDEX_HTML = REPO_ROOT / "templates" / "index.html"


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


# --------------------------------------------------------------------------- #
# README / docs consolidation
# --------------------------------------------------------------------------- #
def test_readme_includes_merged_demo_and_app_demo():
    text = README.read_text(encoding="utf-8")
    assert "make a website for my school robotics club" in text
    assert "make a quiz app about Python basics" in text
    assert "add score tracking" in text
    assert "Demo flow" in text
    # The optional app demo and the 5-minute demo were merged from the demo scripts.
    assert "describe preview" in text


def test_readme_lists_supported_project_types():
    text = README.read_text(encoding="utf-8").lower()
    for project_type in (
        "robotics club",
        "quiz app",
        "calculator app",
        "flashcard",
        "timetable",
        "habit tracker",
        "resume",
    ):
        assert project_type in text, project_type


def test_readme_lists_all_export_artifacts():
    text = README.read_text(encoding="utf-8")
    for artifact in (
        "index.html",
        "style.css",
        "script.js",
        "README.txt",
        "CODE_MAP.txt",
        "STEP_NARRATION.txt",
        "LEARNING_NOTES.txt",
        "PROJECT_SUMMARY.txt",
        "PROJECT_REVIEW.txt",
        "PREVIEW_DESCRIPTION.txt",
        "ACCESSIBILITY_REPORT.txt",
        "TRAINER_NOTES.txt",
        "STUDENT_RECAP.txt",
        "SCREEN_READER_SUMMARY.txt",
        "CHANGE_REPLAY.txt",
        "BOOKMARKS.txt",
    ):
        assert artifact in text, artifact


def test_readme_links_to_security_policy():
    text = README.read_text(encoding="utf-8")
    assert "SECURITY.md" in text
    # The full policy should live in SECURITY.md, not be duplicated into the README.
    assert "Reporting a Vulnerability" not in text


def test_redundant_markdown_files_removed():
    for name in ("DEMO.md", "DEMO_SCRIPT.md", "DEMO_READINESS.md", "HTML_MODE.md"):
        assert not (REPO_ROOT / name).exists(), name
    # Only README.md and SECURITY.md remain at the repo root.
    root_markdown = sorted(p.name for p in REPO_ROOT.glob("*.md"))
    assert root_markdown == ["README.md", "SECURITY.md"], root_markdown


def test_security_policy_exists_and_is_strong():
    assert SECURITY.exists()
    text = SECURITY.read_text(encoding="utf-8")
    assert "Security Policy" in text
    assert "Reporting a Vulnerability" in text
    assert "Content Security Policy" in text
    for guarantee in ("eval", "credential", "phishing", "tracking"):
        assert guarantee in text.lower(), guarantee


# --------------------------------------------------------------------------- #
# Feature routing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("command", "action"),
    [
        ("landmarks", "landmarks"),
        ("list landmarks", "landmarks"),
        ("website landmarks", "landmarks"),
        ("sections", "landmarks"),
        ("show sections", "landmarks"),
        ("replay change", "review_changes"),
        ("what changed", "review_changes"),
        ("make trainer notes", "trainer_notes"),
        ("teacher notes", "trainer_notes"),
        ("what did I learn today", "student_recap"),
        ("session recap", "student_recap"),
        ("learning recap", "student_recap"),
        ("prepare this for NVDA", "screen_reader_prep"),
        ("prepare for screen reader", "screen_reader_prep"),
        ("screen reader summary", "screen_reader_prep"),
        ("start tutorial", "tutorial_start"),
        ("next", "tutorial_control"),
        ("repeat", "tutorial_control"),
        ("exit tutorial", "tutorial_control"),
        ("list bookmarks", "list_bookmarks"),
        # Existing routes must be preserved after the split.
        ("learning notes", "learning_notes"),
        ("what did I build", "project_summary"),
        ("recap", "tutorial_control"),
    ],
)
def test_new_feature_commands_route(client, command, action):
    routed = client.post("/voice-command", json={"text": command}).get_json()
    assert routed["action"] == action, command


def test_bookmark_section_routes_with_name(client):
    routed = client.post("/voice-command", json={"text": "bookmark the contact form as contact area"}).get_json()
    assert routed["action"] == "save_bookmark"
    assert routed["slots"]["name"] == "contact area"

    go = client.post("/voice-command", json={"text": "go to bookmark contact area"}).get_json()
    assert go["action"] == "read_bookmark"


@pytest.mark.parametrize(
    ("typed", "action"),
    [
        ("check accessiblity", "audit_site"),
        ("explane css", "file_explanation"),
        ("export side", "export_site"),
        ("code mapp", "code_map"),
        ("step naration", "step_narration"),
        ("add cantact form", "add_contact_section"),
    ],
)
def test_fuzzy_command_repairs_route_correctly(client, typed, action):
    routed = client.post("/voice-command", json={"text": typed}).get_json()
    assert routed["action"] == action, typed


def test_repair_command_fixes_known_typos():
    assert repair_command("make webside") == "make website"
    assert repair_command("check accessiblity") == "check accessibility"
    assert repair_command("explane css") == "explain css"
    assert repair_command("export side") == "export site"
    assert repair_command("code mapp") == "code map"
    assert repair_command("step naration") == "step narration"
    assert repair_command("add cantact form") == "add contact form"
    assert repair_command("make profeshnal") == "make professional"


# --------------------------------------------------------------------------- #
# New explanation endpoints
# --------------------------------------------------------------------------- #
def test_learning_endpoints_return_artifacts(client):
    files = generate_site_files("make a website for my school robotics club")
    payload = {
        "name": "Robotics",
        "project_type": files["project_type"],
        "html": files["html"],
        "css": files["css"],
        "js": files["js"],
    }
    endpoints = {
        "/project-landmarks": "WEB LANDMARKS",
        "/trainer-notes": "TRAINER NOTES",
        "/student-recap": "STUDENT RECAP",
        "/screen-reader-summary": "SCREEN READER SUMMARY",
    }
    for endpoint, expected in endpoints.items():
        data = client.post(endpoint, json=payload).get_json()
        assert data["success"] is True, endpoint
        assert expected in data["text"], endpoint

    landmarks = client.post("/project-landmarks", json=payload).get_json()["text"]
    assert "This website has" in landmarks


# --------------------------------------------------------------------------- #
# Export additions
# --------------------------------------------------------------------------- #
def _export(client, **extra):
    files = generate_site_files("make a website for my school robotics club")
    body = {
        "name": "Robotics",
        "project_type": files["project_type"],
        "files": {"index.html": files["html"], "style.css": files["css"], "script.js": files["js"]},
    }
    body.update(extra)
    response = client.post("/export-site.zip", json=body)
    assert response.status_code == 200
    return set(zipfile.ZipFile(io.BytesIO(response.data)).namelist())


def test_export_always_includes_new_learner_artifacts(client):
    names = _export(client)
    assert {"TRAINER_NOTES.txt", "STUDENT_RECAP.txt", "SCREEN_READER_SUMMARY.txt"} <= names


def test_export_includes_change_replay_after_edit(client):
    names = _export(
        client,
        change_replay={
            "html_before": "<main><h1>Robo</h1></main>",
            "html_after": "<main><h1>Robo</h1><section><h2>Competitions</h2></section></main>",
            "instruction": "add a section about competitions",
        },
    )
    assert "CHANGE_REPLAY.txt" in names


def test_export_includes_bookmarks_when_present(client):
    names = _export(client, bookmarks={"contact area": {"section": "contact form"}})
    assert "BOOKMARKS.txt" in names


def test_export_omits_conditional_artifacts_when_absent(client):
    names = _export(client)
    assert "CHANGE_REPLAY.txt" not in names
    assert "BOOKMARKS.txt" not in names


def test_change_replay_artifact_describes_the_edit(client):
    files = generate_site_files("make a calculator app")
    response = client.post(
        "/export-site.zip",
        json={
            "name": "Calc",
            "project_type": files["project_type"],
            "files": {"index.html": files["html"], "style.css": files["css"], "script.js": files["js"]},
            "change_replay": {
                "html_before": "<main><h1>Calc</h1></main>",
                "html_after": "<main><h1>Calc</h1><section><h2>History</h2></section></main>",
                "instruction": "add a history section",
            },
        },
    )
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        replay = archive.read("CHANGE_REPLAY.txt").decode("utf-8")
    assert "add a history section" in replay
    assert "section" in replay.lower()


# --------------------------------------------------------------------------- #
# Safety
# --------------------------------------------------------------------------- #
def _looks_like_code(text: str) -> bool:
    lowered = text.lower()
    return "<script" in lowered or "<style" in lowered or "<!doctype" in lowered or "function(" in lowered


def test_screen_reader_summary_does_not_generate_code():
    files = generate_site_files("make a quiz app about Python basics")
    text = build_screen_reader_summary(
        files["html"], files["css"], files["js"], name="Quiz", project_type=files["project_type"]
    )
    assert "SCREEN READER SUMMARY" in text
    assert not _looks_like_code(text)
    assert "eval(" not in text


def test_trainer_notes_recap_and_summaries_do_not_emit_code():
    files = generate_site_files("make a website for my school robotics club")
    for builder in (build_trainer_notes, build_student_recap):
        text = builder(files["html"], files["css"], files["js"], name="Robotics", project_type=files["project_type"])
        assert not _looks_like_code(text)


def test_learning_endpoints_do_not_mutate_website_files(client):
    files = generate_site_files("make a website for my school robotics club")
    payload = {
        "name": "Robotics",
        "project_type": files["project_type"],
        "html": files["html"],
        "css": files["css"],
        "js": files["js"],
    }
    for endpoint in ("/trainer-notes", "/student-recap", "/screen-reader-summary", "/project-landmarks"):
        data = client.post(endpoint, json=payload).get_json()
        # These features explain; they never return modified source files.
        assert "files" not in data
        assert "html" not in data
        assert "code" not in data


def test_command_repair_does_not_alter_generated_code():
    for prompt in ("make a quiz app about Python basics", "make a website for my school robotics club"):
        files = generate_site_files(prompt)
        assert repair_command(files["html"]) == files["html"], prompt
        assert repair_command(files["css"]) == files["css"], prompt
        assert repair_command(files["js"]) == files["js"], prompt


# --------------------------------------------------------------------------- #
# UI / output
# --------------------------------------------------------------------------- #
def test_help_panel_contains_grouped_commands(client):
    html = client.get("/ide").get_data(as_text=True)
    for group in ("Create", "Edit", "Understand", "Accessibility", "Export"):
        assert group in html, group
    for command in (
        "make a website for my school robotics club",
        "code map",
        "landmarks",
        "check accessibility",
        "make trainer notes",
        "export website",
    ):
        assert command in html, command


def test_export_success_message_lists_key_files():
    js = FRONTEND_JS.read_text(encoding="utf-8")
    assert "TRAINER_NOTES.txt" in js
    assert "STUDENT_RECAP.txt" in js
    assert "SCREEN_READER_SUMMARY.txt" in js


def test_output_includes_try_next_suggestions():
    js = FRONTEND_JS.read_text(encoding="utf-8")
    assert "Try this next" in js
    assert "suggestNext" in js


def test_audit_issues_include_severity_and_suggested_fix(client):
    html = "<html><body><main><h1>Demo</h1><button></button><img src='x.png'></main></body></html>"
    audit = client.post("/html-audit", json={"html": html}).get_json()["audit"]
    assert audit["issues"]
    for issue in audit["issues"]:
        assert "severity" in issue
        assert "suggested_fix" in issue
