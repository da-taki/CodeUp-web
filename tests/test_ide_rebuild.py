import io
import json
import zipfile
from pathlib import Path

import pytest

from codeup.services.site_generator import combine_site_files, generate_site_files, parse_file_blocks


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    import app as app_module
    import codeup.config as config_module

    monkeypatch.setattr(config_module, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_parse_file_blocks_and_combine_preview_safe_html():
    parsed = parse_file_blocks(
        """
FILE: index.html
<!doctype html>
<html lang="en">
<head><title>Demo</title><link rel="stylesheet" href="style.css"></head>
<body><main><h1>Demo</h1></main><script src="script.js" defer></script></body>
</html>

FILE: style.css
body { color: #111827; }

FILE: script.js
document.body.dataset.ready = "true";
"""
    )

    assert parsed["html"].startswith("<!doctype html>")
    assert parsed["css"] == "body { color: #111827; }"
    assert parsed["js"] == 'document.body.dataset.ready = "true";'

    combined = combine_site_files(parsed["html"], parsed["css"], parsed["js"])
    assert 'href="style.css"' not in combined
    assert 'src="script.js"' not in combined
    assert "<style>" in combined and parsed["css"] in combined
    assert "<script>" in combined and parsed["js"] in combined


def test_generated_robotics_site_contains_demo_contract_sections():
    files = generate_site_files(
        "generate a website for the robotics lab of my school with projects, achievements, student team, "
        "equipment, events, and a join form"
    )
    combined = combine_site_files(files["html"], files["css"], files["js"]).lower()

    for needle in (
        "hero",
        "robotics lab",
        "mission",
        "projects",
        "achievements",
        "student team",
        "equipment",
        "events",
        "join the lab",
        "data-filter",
        "data-theme-toggle",
        "stat-num",
        "data-nav-toggle",
        "addEventListener",
    ):
        assert needle.lower() in combined


def test_generated_bakery_site_contains_demo_contract_sections():
    files = generate_site_files("generate a website for a bakery")
    combined = combine_site_files(files["html"], files["css"], files["js"]).lower()

    for needle in (
        "hero",
        "menu",
        "specials",
        "our story",
        "reviews",
        "order or say hello",
        "data-filter",
        "data-theme-toggle",
        "data-contact-form",
        "addEventListener",
    ):
        assert needle.lower() in combined


def test_export_project_zip_contains_three_source_files(client):
    response = client.post(
        "/export-site.zip",
        json={
            "name": "Bakery Demo",
            "files": {
                "index.html": "<!doctype html><html lang='en'><head><title>Bakery</title></head><body><h1>Bakery</h1></body></html>",
                "style.css": "body { color: #111827; }",
                "script.js": "document.body.dataset.ready = 'true';",
            },
        },
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        names = set(archive.namelist())
        assert {"index.html", "style.css", "script.js", "README.txt", "manifest.json"} <= names
        assert {
            "CODE_MAP.txt",
            "STEP_NARRATION.txt",
            "LEARNING_NOTES.txt",
            "PROJECT_SUMMARY.txt",
            "ACCESSIBILITY_REPORT.txt",
            "PROJECT_REVIEW.txt",
            "PREVIEW_DESCRIPTION.txt",
        } <= names
        index = archive.read("index.html").decode("utf-8")
        assert 'href="style.css"' in index
        assert 'src="script.js"' in index
        assert archive.read("style.css").decode("utf-8") == "body { color: #111827; }"
        assert "dataset.ready" in archive.read("script.js").decode("utf-8")
        assert "Open index.html in a browser" in archive.read("README.txt").decode("utf-8")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["files"] == ["index.html", "style.css", "script.js"]
        assert "CODE_MAP.txt" in manifest["artifacts"]


def test_fallback_generation_covers_product_categories_and_reports_fallback(client):
    prompts = {
        "make a website for my school robotics club": "robotics",
        "create a personal portfolio website": "portfolio",
        "make a website for a coding workshop": "sessions",
        "create a landing page for an accessibility project": "accessibility",
        "make a simple website for a bakery": "menu",
        "make a website for my science fair project": "project",
    }

    for prompt, expected_text in prompts.items():
        data = client.post("/generate-site", json={"prompt": prompt}).get_json()
        assert data["success"] is True
        assert data["fallback"] is True
        assert "simple accessible starter website" in " ".join(data["summary"])
        combined = combine_site_files(data["html"], data["css"], data["js"]).lower()
        assert "<main" in combined
        assert "<h1" in combined
        assert expected_text in combined


def test_generated_sites_use_restrained_visual_style():
    prompts = (
        "make a website for my school robotics club",
        "make a simple website for a bakery",
        "make a quiz app about web accessibility basics",
    )
    blocked = (
        "linear-gradient",
        "radial-gradient",
        "conic-gradient",
        "background-clip: text",
        "color: transparent",
        "data-count",
        "requestAnimationFrame",
        "\\ufffd",
        "\\u00c2",
        "\\u00e2",
        "\\ud83d",
    )
    for prompt in prompts:
        files = generate_site_files(prompt)
        combined = "\n".join((files["html"], files["css"], files["js"]))
        lowered = combined.lower()
        for pattern in blocked:
            assert pattern.lower() not in lowered, (prompt, pattern)
        assert all(ord(ch) < 128 for ch in combined), prompt
        assert "animation: none !important" in files["css"]
        assert "background: #1f6f8b" in files["css"]


def test_edit_site_updates_existing_project_without_replacing_topic(client):
    files = generate_site_files("make a website for my school robotics club")

    edited = client.post(
        "/edit-site",
        json={
            "instruction": "add a section about competitions",
            "html": files["html"],
            "css": files["css"],
            "js": files["js"],
        },
    ).get_json()

    assert edited["success"] is True
    combined = combine_site_files(edited["html"], edited["css"], edited["js"]).lower()
    assert "competitions" in combined
    assert "robotics" in combined
    assert "bakery" not in combined

    polished = client.post(
        "/edit-site",
        json={
            "instruction": "make it more professional",
            "html": edited["html"],
            "css": edited["css"],
            "js": edited["js"],
        },
    ).get_json()
    assert polished["success"] is True
    assert "line-height: 1.65" in polished["css"]
    assert "Made the visual style more professional." in polished["summary"]
    assert "robotics" in polished["html"].lower()


def test_beginner_followup_edits_are_deterministic(client):
    files = generate_site_files("make a todo list website")

    edited = client.post(
        "/edit-site",
        json={
            "instruction": "add a button",
            "html": files["html"],
            "css": files["css"],
            "js": "",
        },
    ).get_json()
    assert edited["success"] is True
    assert "New button" in edited["html"]

    styled = client.post(
        "/edit-site",
        json={
            "instruction": "change the background color",
            "html": edited["html"],
            "css": edited["css"],
            "js": edited["js"],
        },
    ).get_json()
    assert styled["success"] is True
    assert "background: #eef6ff" in styled["css"]

    commented = client.post(
        "/edit-site",
        json={
            "instruction": "add comments",
            "html": styled["html"],
            "css": styled["css"],
            "js": styled["js"],
        },
    ).get_json()
    assert commented["success"] is True
    assert "CodeUp Web note" not in commented["html"]
    assert "CodeUp Web note" not in commented["css"]
    assert "CodeUp Web note" not in commented["js"]
    assert any("source files clean" in item for item in commented["summary"])
    assert 'id="comments"' not in commented["html"]
    assert "CodeUp Web note" not in commented["html"] + commented["css"] + commented["js"]

    functional = client.post(
        "/edit-site",
        json={
            "instruction": "make it use a function",
            "html": commented["html"],
            "css": commented["css"],
            "js": commented["js"],
        },
    ).get_json()
    assert functional["success"] is True
    assert "function " in functional["js"]


def test_website_validation_rejects_unsafe_scripts_and_raw_transcript_is_escaped():
    from codeup.services.natural_website_editor import plan_website_edit, validate_website_files

    unsafe = validate_website_files(
        {
            "index.html": "<!doctype html><html lang='en'><head><title>X</title></head><body><main><h1>X</h1></main></body></html>",
            "style.css": "a:focus-visible { outline: 3px solid #f59e0b; }",
            "script.js": "eval('alert(1)')",
        }
    )
    assert unsafe.valid is False
    assert any("Dynamic JavaScript" in error for error in unsafe.errors)

    files = generate_site_files("make a website for my robotics club")
    plan = plan_website_edit(
        current_html=files["html"],
        current_css=files["css"],
        current_js=files["js"],
        instruction="add a section about <script>alert(1)</script>",
    )
    assert plan.action == "update_website"
    assert "<script>alert(1)</script>" not in plan.files["index.html"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in plan.files["index.html"]


def test_publish_project_uses_current_editor_html_not_stale_saved_page(client):
    project = client.post(
        "/projects",
        json={"name": "Preview Race", "html": "<h1>Saved project page</h1>"},
    ).get_json()["project"]
    current_html = (
        "<!doctype html><html lang='en'><head><title>Current</title>"
        "<style>.hero { border-top: 9px solid rgb(255, 0, 0); }</style></head>"
        "<body><main class='hero'><h1>Current editor page</h1></main>"
        "<script>window.previewJsFlag = 'yes';</script></body></html>"
    )

    result = client.post(
        "/publish-site",
        json={"project_id": project["id"], "current_page": "home", "html": current_html},
    ).get_json()

    assert result["success"] is True
    hosted = client.get(result["url"]).get_data(as_text=True)
    assert "Current editor page" in hosted
    assert "border-top: 9px" in hosted
    assert "previewJsFlag" in hosted
    assert "Saved project page" not in hosted


def test_voice_command_catalogue_routes_new_ide_commands(client):
    expected = {
        "generate a website for robotics lab of my school": "build_site",
        "make a website about bakery": "build_site",
        "create a landing page for tuition center": "build_site",
        "build a portfolio site for student developer": "build_site",
        "make it more beautiful": "design_preset",
        "make it more futuristic": "design_preset",
        "add dark mode": "darken_theme",
        "add a contact section": "add_contact_section",
        "add a button": "edit_website",
        "change the background color": "edit_css",
        "add comments": "edit_website",
        "make it use a function": "edit_website",
        "add animations": "design_preset",
        "improve the design": "design_preset",
        "make it accessible": "apply_audit_fixes",
        "add JavaScript interactivity": "add_js_interactivity",
        "fix the code": "apply_audit_fixes",
        "read the code": "read_code",
        "read the HTML": "read_code",
        "read the CSS": "read_code",
        "read the JavaScript": "read_code",
        "explain the code": "explain_site",
        "explain the JavaScript": "file_explanation",
        "give me a code map": "code_map",
        "analyze the code": "analyze_code",
        "find problems": "analyze_code",
        "summarize the website": "explain_site",
        "stop everything": "stop_speaking",
        "stop speaking": "stop_speaking",
        "cancel": "stop_speaking",
        "run preview": "preview_site",
        "save snippet as test demo": "save_snippet",
        "load snippet test demo": "load_snippet",
        "delete snippet test demo": "delete_snippet",
    }

    for command, action in expected.items():
        data = client.post("/voice-command", json={"text": command}).get_json()
        assert data["action"] == action, command


def test_frontend_publish_preview_sends_three_source_files():
    js = Path("static/codeup-html.js").read_text(encoding="utf-8")
    assert "body: JSON.stringify({ html: sourceHtml(), css: state.files.css, js: state.files.js" in js
    assert '"index.html": sourceHtml()' in js
    assert '"style.css": state.files.css' in js
    assert '"script.js": state.files.js' in js


def test_frontend_help_more_and_stop_behaviour_are_command_first():
    js = Path("static/codeup-html.js").read_text(encoding="utf-8")
    assert "function moreAction" in js
    assert "function stopActivity" in js
    assert "stop.hidden = !(isBusy || state.voiceActive)" in js
    assert 'runCommand("start tutorial")' in js
    assert "Start tutorial" not in Path("templates/index.html").read_text(encoding="utf-8").split('id="moreMenu"')[0]
