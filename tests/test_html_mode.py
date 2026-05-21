import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    import app as app_module

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_root_is_html_builder(client):
    response = client.get("/")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "CODEUP HTML" in body
    assert "Ask / Build" in body
    assert "Blind-first website builder" in body
    assert "legacy code execution IDE" not in body


def test_healthz(client):
    data = client.get("/healthz").get_json()
    assert data["status"] == "ok"
    assert data["version"].endswith("-html")


def test_publish_site_wraps_fragment_and_serves_locally(client):
    response = client.post("/publish-site", json={"html": "<h1>Science Fair</h1>"})
    data = response.get_json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["url"].startswith("/student-site/")

    hosted = client.get(data["url"])
    hosted_body = hosted.get_data(as_text=True)
    assert hosted.status_code == 200
    assert "<!doctype html>" in hosted_body.lower()
    assert "Science Fair" in hosted_body


def test_html_memory_persists_per_session(client):
    saved = client.post(
        "/html-memory",
        json={"prompt": "Build a website for art club", "html": "<html>Art</html>", "url": "/student-site/demo/"},
    ).get_json()
    assert saved["success"] is True

    loaded = client.get("/html-memory").get_json()
    assert loaded["memory"]["last_html"] == "<html>Art</html>"
    assert loaded["memory"]["last_url"] == "/student-site/demo/"
    assert loaded["memory"]["history"][-1]["prompt"] == "Build a website for art club"


def test_chat_uses_memory_and_has_local_fallback_without_ai(client):
    response = client.post(
        "/html-chat",
        json={"message": "Hello what can I do here?", "html": "<html><body><h1>Club</h1></body></html>"},
    )
    data = response.get_json()
    assert response.status_code == 200
    assert data["success"] is True
    assert "CodeUp HTML" in data["reply"]
    assert "build a website" in data["reply"].lower()
    assert data["memory"]["history"][-1]["note"] == "chat"


def test_generate_code_has_local_html_fallback_without_ai(client):
    response = client.post("/generate-code", json={"prompt": "Build a website for a robotics club"})
    data = response.get_json()
    assert response.status_code == 200
    assert data["success"] is True
    assert "<!doctype html>" in data["code"].lower()
    assert "Robotics Club" in data["code"]


def test_analyze_and_fix_have_local_fallbacks_without_ai(client):
    html = "<h1>Robotics Club</h1><p>Welcome</p>"
    analyzed = client.post("/analyze", json={"code": html}).get_json()
    fixed = client.post("/fix", json={"code": html}).get_json()
    assert analyzed["success"] is True
    assert "Robotics Club" in analyzed["analysis"]
    assert fixed["success"] is True
    assert "<!doctype html>" in fixed["code"].lower()


def test_analyze_and_fix_validate_html(client):
    empty_analyze = client.post("/analyze", json={"code": "   "})
    empty_fix = client.post("/fix", json={"code": "   "})
    assert empty_analyze.status_code == 400
    assert empty_fix.status_code == 400


def test_voice_command_is_html_or_chat_focused(client):
    assert client.post("/voice-command", json={"text": "preview website"}).get_json()["action"] == "preview_site"
    assert client.post("/voice-command", json={"text": "explain website"}).get_json()["action"] == "explain_site"
    assert client.post("/voice-command", json={"text": "build a website for music class"}).get_json()["action"] == "build_site"
    assert client.post("/voice-command", json={"text": "what is missing in this website?"}).get_json()["action"] == "chat"


def test_legacy_execution_routes_are_gone(client):
    legacy_run_route = "/" + "run"
    assert client.post(legacy_run_route, json={"code": "legacy"}).status_code == 404
    assert client.post("/structure", json={"code": "legacy"}).status_code == 404


def test_same_origin_blocks_cross_site_posts(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "false")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    import app as app_module

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    test_client = app_module.app.test_client()
    response = test_client.post(
        "/html-chat",
        json={"message": "hello"},
        headers={"Origin": "https://evil.example", "Host": "localhost"},
    )
    assert response.status_code == 403
