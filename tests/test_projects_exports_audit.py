import io
import json
import zipfile
from pathlib import Path

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    import app as app_module
    import codeup.config as config_module

    monkeypatch.setattr(config_module, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_app_data_dirs_are_created_under_configured_data_dir(monkeypatch, tmp_path):
    import codeup.config as config_module
    from codeup.storage import init_data_dirs

    monkeypatch.setattr(config_module, "DATA_DIR", str(tmp_path / "data"))
    init_data_dirs()

    for name in ("projects", "html_memory", "student_sites", "exports", "tmp"):
        assert (tmp_path / "data" / name).is_dir()
    assert not (tmp_path / "projects").exists()


def test_project_create_list_update_duplicate_and_versions(client, tmp_path):
    created = client.post(
        "/projects",
        json={"name": "Robotics Club", "pages": {"home": "<h1>Home</h1>"}, "current_page": "home"},
    )
    assert created.status_code == 201
    project = created.get_json()["project"]
    project_id = project["id"]
    assert project["name"] == "Robotics Club"
    assert len(project["versions"]) == 1

    saved_file = Path(tmp_path) / "projects" / f"{project_id}.json"
    assert saved_file.exists()
    assert json.loads(saved_file.read_text(encoding="utf-8"))["pages"]["home"] == "<h1>Home</h1>"

    updated = client.patch(
        f"/projects/{project_id}",
        json={"name": "Robotics Team", "pages": {"home": "<h1>Updated</h1>"}, "current_page": "home"},
    ).get_json()
    assert updated["project"]["name"] == "Robotics Team"
    assert updated["project"]["pages"]["home"] == "<h1>Updated</h1>"

    version = client.post(
        f"/projects/{project_id}/versions",
        json={
            "label": "Manual Edit",
            "source": "test",
            "pages": {"home": "<h1>Version Two</h1>"},
            "summary": ["Changed heading."],
        },
    )
    assert version.status_code == 201

    versions = client.get(f"/projects/{project_id}/versions").get_json()["versions"]
    assert [item["label"] for item in versions] == ["Initial version", "Manual Edit"]
    assert versions[-1]["summary"] == ["Changed heading."]

    restored = client.post(f"/projects/{project_id}/versions/{versions[0]['id']}/restore").get_json()
    assert restored["project"]["pages"]["home"] == "<h1>Home</h1>"
    assert restored["project"]["versions"][-1]["source"] == "restore"

    duplicate = client.post(f"/projects/{project_id}/duplicate", json={"name": "Robotics Copy"})
    assert duplicate.status_code == 201
    assert duplicate.get_json()["project"]["name"] == "Robotics Copy"

    listing = client.get("/projects").get_json()["projects"]
    assert {item["name"] for item in listing} >= {"Robotics Team", "Robotics Copy"}
    assert all("versions" in item and item["versions"] == [] for item in listing)


def test_autosave_persists_name_change(client):
    created = client.post(
        "/projects",
        json={"name": "Original Name", "pages": {"home": "<h1>Home</h1>"}, "current_page": "home"},
    )
    project_id = created.get_json()["project"]["id"]

    autosaved = client.post(
        f"/projects/{project_id}/autosave",
        json={"name": "Renamed via Autosave", "pages": {"home": "<h1>Updated</h1>"}, "current_page": "home"},
    )
    assert autosaved.status_code == 200
    assert autosaved.get_json()["project"]["name"] == "Renamed via Autosave"

    loaded = client.get(f"/projects/{project_id}").get_json()["project"]
    assert loaded["name"] == "Renamed via Autosave"
    assert loaded["pages"]["home"] == "<h1>Updated</h1>"


def test_autosave_without_name_preserves_existing_name(client):
    created = client.post(
        "/projects",
        json={"name": "Keep This Name", "pages": {"home": "<h1>Home</h1>"}, "current_page": "home"},
    )
    project_id = created.get_json()["project"]["id"]

    autosaved = client.post(
        f"/projects/{project_id}/autosave",
        json={"pages": {"home": "<h1>Changed</h1>"}, "current_page": "home"},
    )
    assert autosaved.get_json()["project"]["name"] == "Keep This Name"


def test_publish_updates_project_version_and_zip_export_contains_pages(client):
    project = client.post(
        "/projects",
        json={"name": "School Fair", "pages": {"home": "<h1>Home</h1>", "about": "<h1>About</h1>"}},
    ).get_json()["project"]

    publish = client.post(
        "/publish-site",
        json={
            "project_id": project["id"],
            "pages": {
                "home": "<h1>Home</h1><a href='about.html'>About</a>",
                "about": "<h1>About</h1>",
            },
        },
    ).get_json()
    assert publish["success"] is True
    versions = client.get(f"/projects/{project['id']}/versions").get_json()["versions"]
    assert versions[-1]["source"] == "publish"

    response = client.post(
        "/export-site.zip",
        json={
            "project_id": project["id"],
            "name": "School Fair",
            "pages": {"home": "<h1>Home</h1><a href='about.html'>About</a>", "about": "<h1>About</h1>"},
        },
    )
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("application/zip")
    assert "attachment" in response.headers["Content-Disposition"]

    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert set(archive.namelist()) == {"index.html", "about.html", "manifest.json"}
        assert "href='about.html'" in archive.read("index.html").decode("utf-8")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["pages"]["home"] == "index.html"


def test_publish_returns_warnings_when_external_resources_stripped(client):
    html_with_external = (
        "<html><head>"
        '<link rel="stylesheet" href="https://cdn.example.com/style.css">'
        "</head><body>"
        '<script src="https://cdn.example.com/app.js"></script>'
        "<h1>Hello</h1></body></html>"
    )
    result = client.post("/publish-site", json={"html": html_with_external}).get_json()
    assert result["success"] is True
    assert "warnings" in result
    assert len(result["warnings"]) == 2
    assert any("style.css" in w for w in result["warnings"])
    assert any("app.js" in w for w in result["warnings"])


def test_publish_no_warnings_for_clean_html(client):
    result = client.post("/publish-site", json={"html": "<h1>Clean</h1>"}).get_json()
    assert result["success"] is True
    assert "warnings" not in result


def test_parser_audit_reports_structured_issues_and_autofix_snapshots(client):
    project = client.post("/projects", json={"name": "Audit Demo", "html": "<h1>Seed</h1>"}).get_json()["project"]
    html = "<html><head><title></title></head><body><img src='hero.png'><button></button><p>Hello</p></body></html>"

    audit = client.post("/html-audit", json={"html": html, "project_id": project["id"]}).get_json()["audit"]
    issue_ids = {issue["id"] for issue in audit["issues"]}
    assert {"missing_doctype", "missing_lang", "missing_title", "missing_viewport", "missing_image_alt"} <= issue_ids
    assert all("suggested_fix" in issue for issue in audit["issues"])

    fixed = client.post(
        "/audit-autofix",
        json={"html": html, "project_id": project["id"], "fix_all": True},
    ).get_json()
    assert fixed["success"] is True
    assert 'alt="Describe this image"' in fixed["code"]
    assert "<button>Button</button>" in fixed["code"]
    assert fixed["fixed"]
    assert fixed["summary"]
    remaining_ids = {issue["id"] for issue in fixed["audit"]["issues"]}
    assert "missing_title" not in remaining_ids
    assert "missing_image_alt" not in remaining_ids

    versions = client.get(f"/projects/{project['id']}/versions").get_json()["versions"]
    assert versions[-2]["source"] == "audit-autofix-before"
    assert versions[-1]["source"] == "audit-autofix-after"


def test_audit_autofix_repairs_empty_existing_lang_title_and_alt(client):
    html = (
        "<!doctype html><html lang=''><head><title> </title>"
        "<meta name='viewport' content='width=device-width'></head>"
        "<body><main><h1>Gallery</h1><img src='hero.png' alt='  '></main></body></html>"
    )

    fixed = client.post("/audit-autofix", json={"html": html, "fix_all": True}).get_json()
    remaining_ids = {issue["id"] for issue in fixed["audit"]["issues"]}

    assert fixed["success"] is True
    assert 'lang="en"' in fixed["code"]
    assert "<title>CodeUp Project</title>" in fixed["code"]
    assert 'alt="Describe this image"' in fixed["code"]
    assert {"missing_lang", "missing_title", "missing_image_alt"}.isdisjoint(remaining_ids)


def test_audit_autofix_labels_only_unlabeled_form_controls(client):
    html = (
        "<!doctype html><html lang='en'><head><title>Form</title>"
        "<meta name='viewport' content='width=device-width'></head>"
        "<body><main><h1>Form</h1>"
        "<label for='named'>Name</label><input id='named'>"
        "<textarea></textarea><select aria-label='  '><option>One</option></select>"
        "</main></body></html>"
    )

    fixed = client.post("/audit-autofix", json={"html": html, "fix_all": True}).get_json()
    remaining_ids = {issue["id"] for issue in fixed["audit"]["issues"]}

    assert fixed["success"] is True
    assert "<input id='named'>" in fixed["code"]
    assert '<textarea aria-label="Input field">' in fixed["code"]
    assert '<select aria-label="Input field">' in fixed["code"]
    assert "missing_form_label" not in remaining_ids


def test_voice_command_uses_structured_intent_router(client):
    routed = client.post("/voice-command", json={"text": "add contact page"}).get_json()
    assert routed["action"] == "add_contact_page"
    assert routed["slots"]["page"] == "contact"
    assert routed["confidence"] > 0.9

    fixes = client.post("/voice-command", json={"text": "apply all safe fixes"}).get_json()
    assert fixes["action"] == "apply_audit_fixes"

    chat = client.post("/voice-command", json={"text": "tell me about good website colors"}).get_json()
    assert chat["action"] == "chat"
