import io
import json
import zipfile

import pytest

from codeup.services.natural_website_editor import plan_website_edit, validate_website_files
from codeup.services.project_type_router import ALLOWED_PROJECT_TYPES, classify_project_type
from codeup.services.site_generator import generate_site_files


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


def test_project_type_router_uses_allowlist_and_safe_fallback(monkeypatch):
    quiz = classify_project_type("make a quiz app about web accessibility basics", use_ai=False)
    assert quiz.project_type == "quiz_app"
    assert quiz.project_type in ALLOWED_PROJECT_TYPES

    bakery = classify_project_type("build a bakery website", use_ai=False)
    assert bakery.project_type == "bakery"

    import codeup.services.project_type_router as router

    monkeypatch.setattr(
        router, "call_ai", lambda *_args, **_kwargs: '{"project_type":"unsafe_new_type","confidence":0.99}'
    )
    fallback = classify_project_type("make a task list", use_ai=True)
    assert fallback.project_type == "todo_app"

    monkeypatch.setattr(router, "call_ai", lambda *_args, **_kwargs: '{"project_type":"poll_page","confidence":0.91}')
    ai_result = classify_project_type("let students vote", use_ai=True)
    assert ai_result.project_type == "poll_page"
    assert ai_result.source == "ai"


@pytest.mark.parametrize(
    ("prompt", "project_type", "needles"),
    [
        ("make a quiz app about web accessibility basics", "quiz_app", ("quiz-score", "addEventListener", "questions")),
        ("make a calculator app", "calculator_app", ("Calculate", "Cannot divide by zero", "operation")),
        ("make a todo app for homework", "todo_app", ("task-list", "Clear completed", "addEventListener")),
        ("make flashcards for biology", "flashcard_app", ("show-answer", "Next card", "cards")),
        ("make a poll page", "poll_page", ("data-choice", "Poll results", "votes")),
        ("make a contact form", "contact_form", ("contact-email", "aria-live", "does not transmit data")),
        ("make a dashboard for learning stats", "dashboard", ("metric-grid", "Accessibility score", "renderMetrics")),
        ("make a class timetable", "timetable", ("Weekly timetable", "data-day", "renderTimetable")),
        ("make a habit tracker", "habit_tracker", ("habit-list", "habit-meter", "updateHabits")),
    ],
)
def test_generated_project_app_templates_are_safe(prompt, project_type, needles, monkeypatch):
    monkeypatch.setenv("AI_CLOUD_ENABLED", "0")
    files = generate_site_files(prompt)
    combined = "\n".join((files["html"], files["css"], files["js"]))

    assert files["project_type"] == project_type
    for needle in needles:
        assert needle in combined
    assert "eval(" not in files["js"]
    assert "fetch(" not in files["js"]
    validation = validate_website_files(
        {"index.html": files["html"], "style.css": files["css"], "script.js": files["js"]}
    )
    assert validation.valid, validation.errors


def test_project_explanation_routes_return_beginner_artifacts(client):
    files = generate_site_files("make a quiz app about web accessibility basics")
    payload = {
        "name": "Accessibility Quiz",
        "project_type": files["project_type"],
        "html": files["html"],
        "css": files["css"],
        "js": files["js"],
    }

    endpoints = {
        "/project-code-map": "WEB CODE MAP",
        "/project-step-narration": "STEP NARRATION",
        "/project-file-explanation": "SCRIPT.JS EXPLANATION",
        "/project-learning-notes": "LEARNING NOTES",
        "/project-accessibility-map": "ACCESSIBILITY MAP",
        "/project-review": "PROJECT REVIEW",
        "/preview-description": "PREVIEW DESCRIPTION",
        "/project-summary": "PROJECT SUMMARY",
    }

    for endpoint, expected in endpoints.items():
        body = payload | ({"file": "script.js"} if endpoint == "/project-file-explanation" else {})
        data = client.post(endpoint, json=body).get_json()
        assert data["success"] is True, endpoint
        text = data.get("text") or data.get("summary") or ""
        assert expected in text


def test_new_project_voice_commands_route(client):
    expected = {
        "make a quiz app about web accessibility basics": "build_site",
        "website map": "code_map",
        "what files are here": "code_map",
        "step narration": "step_narration",
        "explain CSS": "file_explanation",
        "learning notes": "learning_notes",
        "accessibility map": "accessibility_map",
        "review project": "review_project",
        "describe preview": "describe_preview",
        "what did I build": "project_summary",
    }

    for command, action in expected.items():
        routed = client.post("/voice-command", json={"text": command}).get_json()
        assert routed["action"] == action, command


def test_export_creates_explanation_artifacts_without_prior_generation(client):
    files = generate_site_files("make a calculator app")
    response = client.post(
        "/export-site.zip",
        json={
            "name": "Calculator Demo",
            "project_type": files["project_type"],
            "files": {"index.html": files["html"], "style.css": files["css"], "script.js": files["js"]},
        },
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        names = set(archive.namelist())
        assert {
            "CODE_MAP.txt",
            "STEP_NARRATION.txt",
            "LEARNING_NOTES.txt",
            "PROJECT_SUMMARY.txt",
            "ACCESSIBILITY_REPORT.txt",
            "PROJECT_REVIEW.txt",
            "PREVIEW_DESCRIPTION.txt",
        } <= names
        assert "calculator" in archive.read("PROJECT_SUMMARY.txt").decode("utf-8").lower()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["project_type"] == "calculator_app"


def test_score_tracking_edit_is_idempotent_for_quiz(monkeypatch):
    monkeypatch.setenv("AI_CLOUD_ENABLED", "0")
    files = generate_site_files("make a quiz app about web accessibility basics")
    plan = plan_website_edit(
        current_html=files["html"],
        current_css=files["css"],
        current_js=files["js"],
        instruction="add score tracking",
    )

    assert plan.action == "update_website"
    assert "already present" in plan.summary
    assert "quiz-score" in plan.files["index.html"]
