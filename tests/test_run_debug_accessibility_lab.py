import io
import re
import zipfile

import pytest

from codeup.services.site_generator import generate_site_files
from codeup.services.tutorial_modules import resolve_track, tutorial_tracks
from codeup.services.version_history import build_version_history_report, normalize_versions
from codeup.services.website_accessibility_lab import (
    build_keyboard_test,
    build_readiness_score,
    build_screen_reader_tour,
    build_visual_description,
)
from codeup.services.website_debugger import apply_safe_js_fixes, build_debug_report, collect_issues
from codeup.services.website_runner import NO_WEBSITE_MESSAGE, build_run_summary


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


@pytest.mark.parametrize(
    ("command", "action"),
    [
        ("run website", "run_summary"),
        ("test website", "run_summary"),
        ("run this website", "run_summary"),
        ("check if this website works", "run_summary"),
        ("debug this website", "debug_website"),
        ("debug JavaScript", "debug_website"),
        ("why is this website broken", "debug_website"),
        ("check console errors", "debug_website"),
        ("fix website error", "debug_fix"),
        ("screen reader tour", "screen_reader_tour"),
        ("reading order tour", "screen_reader_tour"),
        ("NVDA tour", "screen_reader_tour"),
        ("test keyboard navigation", "keyboard_test"),
        ("keyboard test", "keyboard_test"),
        ("tab order", "keyboard_test"),
        ("focus order", "keyboard_test"),
        ("describe the design", "visual_description"),
        ("visual description", "visual_description"),
        ("what does the website look like", "visual_description"),
        ("describe colors", "visual_description"),
        ("readiness score", "readiness_score"),
        ("is this ready to share", "readiness_score"),
        ("is this website good", "readiness_score"),
        ("should I share this website", "readiness_score"),
        ("show history", "version_history"),
        ("version history", "version_history"),
        ("undo last change", "undo_version"),
        ("restore previous version", "undo_version"),
        ("compare versions", "review_changes"),
        ("improve like a teacher", "teacher_review"),
        ("suggest improvements", "teacher_review"),
        ("teacher review", "teacher_review"),
        ("start HTML tutorial", "tutorial_start"),
        ("start CSS tutorial", "tutorial_start"),
        ("start JavaScript tutorial", "tutorial_start"),
        ("start accessibility tutorial", "tutorial_start"),
        ("start forms tutorial", "tutorial_start"),
        ("start export tutorial", "tutorial_start"),
        ("describe preview", "describe_preview"),
        ("review project", "review_project"),
        ("what did I build", "project_summary"),
        ("check accessibility", "audit_site"),
    ],
)
def test_lab_commands_route(client, command, action):
    routed = client.post("/voice-command", json={"text": command}).get_json()
    assert routed["action"] == action, command


def test_tutorial_track_slot(client):
    routed = client.post("/voice-command", json={"text": "start accessibility tutorial"}).get_json()
    assert routed["slots"]["track"] == "accessibility"


def test_run_summary_without_website_clarifies():
    assert build_run_summary("", "", "") == NO_WEBSITE_MESSAGE
    assert build_run_summary("<p>   </p>", "", "").startswith("I can test a website")


def test_run_summary_reports_structure(client):
    data = client.post("/run-summary", json=_payload(ROBOTICS)).get_json()
    text = data["text"]
    assert "WEBSITE RUN SUMMARY" in text
    assert "section(s)" in text and "button(s)" in text and "form(s)" in text
    assert "CSS is present" in text


def test_run_summary_detects_interactivity():
    text = build_run_summary(QUIZ["html"], QUIZ["css"], QUIZ["js"], project_type=QUIZ["project_type"])
    assert "JavaScript is present" in text


def test_debugger_detects_missing_dom_id():
    js = "var b = document.getElementById('submitBtn'); b.addEventListener('click', function(){});"
    ids = [issue["id"] for issue in collect_issues("<button>Send</button>", "", js)]
    assert "missing_dom_id" in ids


def test_debugger_detects_duplicate_id():
    html = '<main><h1 id="t">A</h1><h2 id="t">B</h2></main>'
    ids = [issue["id"] for issue in collect_issues(html, "", "")]
    assert "duplicate_id" in ids


def test_debugger_flags_eval():
    ids = [issue["id"] for issue in collect_issues("<main></main>", "", "var x = eval('1+1');")]
    assert "unsafe_js" in ids


def test_debugger_detects_missing_aria_live_when_relevant():
    js = "document.querySelector('#out').textContent = 'done';"
    html = '<main><div id="out"></div></main>'
    ids = [issue["id"] for issue in collect_issues(html, "", js)]
    assert "missing_aria_live" in ids


def test_debugger_honest_when_clean():
    report = build_debug_report(ROBOTICS["html"], ROBOTICS["css"], ROBOTICS["js"])
    assert "did not find obvious website errors" in report["text"]


def test_safe_fix_adds_id_without_unsafe_code():
    result = apply_safe_js_fixes("<button>Go</button>", "", "document.getElementById('goBtn')")
    assert result["changed"] is True
    assert 'id="goBtn"' in result["html"]
    assert "eval(" not in result["html"]
    assert "new Function" not in result["html"]


def test_safe_fix_never_introduces_eval(client):

    result = client.post(
        "/debug-fix",
        json={"html": "<button>Go</button>", "css": "", "js": "eval('x'); document.getElementById('goBtn')"},
    ).get_json()
    assert "eval(" not in result["html"] or result["html"] == "<button>Go</button>"


def test_screen_reader_tour_includes_structure():
    tour = build_screen_reader_tour(
        ROBOTICS["html"], ROBOTICS["css"], ROBOTICS["js"], project_type=ROBOTICS["project_type"]
    )
    assert "SCREEN READER TOUR" in tour
    assert "page title" in tour.lower()
    assert "Heading order" in tour
    assert "Landmarks in order" in tour
    assert "Buttons in order" in tour


def test_screen_reader_tour_warns_on_vague_link():
    html = '<main><h1>Demo</h1><a href="#">click here</a></main>'
    tour = build_screen_reader_tour(html, "", "")
    assert "vague" in tour.lower()


def test_keyboard_test_lists_focusable_and_tab_order():
    html = '<nav><a href="#a">Home</a></nav><main><button>Join</button><form><input id="n"></form></main>'
    report = build_keyboard_test(html, "a:focus { outline: 2px; }", "")
    assert "KEYBOARD NAVIGATION TEST" in report
    assert "keyboard-focusable element" in report
    assert "likely tab order" in report.lower()
    assert "visible focus style" in report


def test_keyboard_test_warns_missing_focus_empty_button_and_clickable_div():
    html = '<main><button></button><div onclick="go()">Card</div></main>'
    report = build_keyboard_test(html, "", "")
    assert "Add a visible :focus" in report
    assert "empty" in report.lower()
    assert "not a button or link" in report


def test_visual_description_describes_layout_colors_sections():
    desc = build_visual_description(
        ROBOTICS["html"], ROBOTICS["css"], ROBOTICS["js"], project_type=ROBOTICS["project_type"]
    )
    assert "VISUAL DESCRIPTION" in desc
    assert "layout" in desc.lower()
    assert "Color palette" in desc


def test_visual_description_detects_named_colors():
    desc = build_visual_description("<main><h1>Hi</h1></main>", "body { background: navy; color: white; }", "")
    assert "navy" in desc.lower() or "white" in desc.lower()


def test_readiness_score_has_number_breakdown_and_recommendation():
    score = build_readiness_score(
        ROBOTICS["html"], ROBOTICS["css"], ROBOTICS["js"], project_type=ROBOTICS["project_type"]
    )
    match = re.search(r"WEBSITE READINESS SCORE: (\d+)/100", score)
    assert match and 0 <= int(match.group(1)) <= 100
    assert "Category breakdown:" in score
    assert "Accessibility:" in score and "Keyboard usability:" in score
    assert "Recommendation:" in score


def test_readiness_reacts_to_keyboard_signal():
    good = build_readiness_score("<main><h1>A</h1><h2>B</h2><footer>f</footer></main>", "button:focus{outline:2px}", "")
    bad = build_readiness_score('<main><h1>A</h1><div onclick="x">c</div></main>', "", "")
    good_score = int(re.search(r"(\d+)/100", good).group(1))
    bad_score = int(re.search(r"(\d+)/100", bad).group(1))
    assert good_score > bad_score


def test_version_history_report_lists_versions(client):
    versions = [
        {"label": "Generated website", "command": "make a quiz app", "summary": ["Built quiz"]},
        {"label": "Edited website", "command": "add score tracking", "summary": ["Added score"]},
    ]
    data = client.post("/version-history", json={"versions": versions}).get_json()
    assert "VERSION HISTORY" in data["text"]
    assert "make a quiz app" in data["text"]
    assert "add score tracking" in data["text"]


def test_version_history_is_bounded():
    many = [{"label": f"v{i}", "command": f"cmd {i}"} for i in range(25)]
    assert len(normalize_versions(many)) == 10
    report = build_version_history_report(many)
    assert "10 saved version" in report


def test_version_history_empty_message():
    assert "No saved versions yet" in build_version_history_report([])


def test_tutorial_tracks_cover_all_paths(client):
    tracks = client.get("/tutorial/tracks").get_json()["tracks"]
    assert set(tracks) == {"html", "css", "javascript", "accessibility", "forms", "export"}
    for track in tracks.values():
        assert track["steps"]
        for step in track["steps"]:
            assert step["title"] and step["command"]


def test_tutorial_tracks_steps_are_web_relevant():
    tracks = tutorial_tracks()
    html_commands = [step["command"] for step in tracks["html"]["steps"]]
    assert any("code map" in cmd for cmd in html_commands)
    a11y_commands = [step["command"] for step in tracks["accessibility"]["steps"]]
    assert any("accessibility" in cmd for cmd in a11y_commands)
    assert resolve_track("start javascript tutorial") == "javascript"
    assert resolve_track("start forms tutorial") == "forms"


def test_export_includes_new_reports(client):
    response = client.post(
        "/export-site.zip",
        json={
            "name": "Quiz",
            "project_type": QUIZ["project_type"],
            "files": {"index.html": QUIZ["html"], "style.css": QUIZ["css"], "script.js": QUIZ["js"]},
            "versions": [{"label": "Generated website", "command": "make a quiz app", "summary": ["init"]}],
        },
    )
    assert response.status_code == 200
    names = set(zipfile.ZipFile(io.BytesIO(response.data)).namelist())
    assert {
        "RUN_SUMMARY.txt",
        "DEBUG_REPORT.txt",
        "SCREEN_READER_TOUR.txt",
        "KEYBOARD_TEST.txt",
        "VISUAL_DESCRIPTION.txt",
        "READINESS_SCORE.txt",
        "VERSION_HISTORY.txt",
        "TEACHER_REVIEW.txt",
    } <= names

    assert {"CODE_MAP.txt", "TRAINER_NOTES.txt", "SCREEN_READER_SUMMARY.txt"} <= names


def test_export_version_history_conditional(client):
    response = client.post(
        "/export-site.zip",
        json={
            "name": "Quiz",
            "project_type": QUIZ["project_type"],
            "files": {"index.html": QUIZ["html"], "style.css": QUIZ["css"], "script.js": QUIZ["js"]},
        },
    )
    names = set(zipfile.ZipFile(io.BytesIO(response.data)).namelist())
    assert "VERSION_HISTORY.txt" not in names


def test_lab_endpoints_do_not_mutate_files(client):
    for endpoint in (
        "/run-summary",
        "/debug-report",
        "/screen-reader-tour",
        "/keyboard-test",
        "/visual-description",
        "/readiness-score",
        "/teacher-review",
    ):
        data = client.post(endpoint, json=_payload(ROBOTICS)).get_json()
        assert data["success"] is True
        assert "files" not in data
        assert "html" not in data
        assert "code" not in data


def test_screen_reader_tour_does_not_emit_code():
    tour = build_screen_reader_tour(QUIZ["html"], QUIZ["css"], QUIZ["js"])
    assert "<script" not in tour.lower()
    assert "eval(" not in tour


def test_teacher_review_is_suggestions_only(client):
    data = client.post("/teacher-review", json=_payload(ROBOTICS)).get_json()
    assert data["success"] is True
    assert "TEACHER REVIEW" in data["text"]
    assert "apply the first suggestion" in data["text"]
    assert isinstance(data["suggestions"], list)

    assert "files" not in data and "html" not in data
