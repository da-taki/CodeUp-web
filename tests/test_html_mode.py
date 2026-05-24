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
    assert "Demo Mode" in body
    assert "Audit" in body
    assert "Export" in body
    assert "Reset" in body
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


def test_reset_session_clears_memory_and_local_site(client):
    published = client.post("/publish-site", json={"html": "<h1>Reset Me</h1>"}).get_json()
    assert client.get(published["url"]).status_code == 200

    reset = client.post("/reset-session", json={"url": published["url"]}).get_json()
    assert reset["success"] is True
    assert reset["memory"] == {"history": [], "last_html": "", "last_url": "", "last_review": ""}
    assert client.get(published["url"]).status_code == 404


def test_html_audit_scores_accessibility(client):
    html = "<!doctype html><html lang='en'><head><title>Club</title><meta name='viewport' content='width=device-width'></head><body><main><h1>Club</h1><button>Join</button></main></body></html>"
    data = client.post("/html-audit", json={"html": html}).get_json()
    assert data["success"] is True
    assert data["audit"]["score"] >= 80
    assert data["audit"]["total"] == len(data["audit"]["checks"])
    assert data["audit"]["contrast_pairs"]
    assert data["audit"]["screen_reader_checks"]


def test_html_audit_reports_contrast_and_screen_reader_patterns(client):
    html = """<!doctype html><html lang='en'><head><title>Low Contrast</title><meta name='viewport' content='width=device-width'><style>
    body { color: #777777; background: #777777; }
    </style></head><body><main><h1>Club</h1><h3>Skipped</h3><button></button></main></body></html>"""
    data = client.post("/html-audit", json={"html": html}).get_json()
    assert data["success"] is True
    assert data["audit"]["contrast_pairs"][0]["ratio"] == 1.0
    assert data["audit"]["contrast_pairs"][0]["passes_aa"] is False
    assert any(check["pattern"] == "NVDA heading navigation" and check["passed"] is False for check in data["audit"]["screen_reader_checks"])
    assert any(check["pattern"] == "VoiceOver control names" and check["passed"] is False for check in data["audit"]["screen_reader_checks"])


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


def test_review_site_has_blind_first_fallback_and_memory(client):
    html = "<!doctype html><html lang='en'><head><title>Club</title></head><body><main><h1>Robotics Club</h1><p>Welcome</p></main></body></html>"
    response = client.post("/review-site", json={"html": html})
    data = response.get_json()
    assert response.status_code == 200
    assert data["success"] is True
    assert "Visual review" in data["review"]
    assert "missing" in data["review"].lower()
    assert data["memory"]["last_review"] == data["review"]


def test_apply_review_updates_html_from_latest_review(client):
    html = "<!doctype html><html lang='en'><head><title>Club</title></head><body><main><h1>Robotics Club</h1></main></body></html>"
    review = client.post("/review-site", json={"html": html}).get_json()["review"]
    response = client.post("/apply-review", json={"html": html, "instruction": "add that", "review": review})
    data = response.get_json()
    assert response.status_code == 200
    assert data["success"] is True
    assert "Next Steps" in data["code"]
    assert "Contact the team" in data["code"]
    assert data["memory"]["history"][-1]["note"] == "Applied review suggestions"


def test_voice_command_is_html_or_chat_focused(client):
    assert client.post("/voice-command", json={"text": "preview website"}).get_json()["action"] == "preview_site"
    assert client.post("/voice-command", json={"text": "audit website"}).get_json()["action"] == "audit_site"
    assert client.post("/voice-command", json={"text": "outline website"}).get_json()["action"] == "outline_site"
    assert client.post("/voice-command", json={"text": "export website"}).get_json()["action"] == "export_site"
    assert client.post("/voice-command", json={"text": "reset session"}).get_json()["action"] == "reset_session"
    assert client.post("/voice-command", json={"text": "explain website"}).get_json()["action"] == "explain_site"
    assert client.post("/voice-command", json={"text": "build a website for music class"}).get_json()["action"] == "build_site"
    assert client.post("/voice-command", json={"text": "what is missing in this website?"}).get_json()["action"] == "review_site"
    assert client.post("/voice-command", json={"text": "add that"}).get_json()["action"] == "apply_review"
    assert client.post("/voice-command", json={"text": "set wake word to table one"}).get_json()["action"] == "set_wake_word"
    assert client.post("/voice-command", json={"text": "next heading"}).get_json()["action"] == "navigate_page"
    assert client.post("/voice-command", json={"text": "make the heading bigger"}).get_json()["action"] == "edit_css"
    assert client.post("/voice-command", json={"text": "what is a div"}).get_json()["action"] == "explain_concept"
    assert client.post("/voice-command", json={"text": "go back two steps"}).get_json()["action"] == "undo_version"
    assert client.post("/voice-command", json={"text": "what changed"}).get_json()["action"] == "review_changes"
    assert client.post("/voice-command", json={"text": "use the science project template"}).get_json()["action"] == "use_template"
    assert client.post("/voice-command", json={"text": "create a multi page website"}).get_json()["action"] == "create_multipage_site"


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
