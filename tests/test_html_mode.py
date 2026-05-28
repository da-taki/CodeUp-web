from http.cookies import SimpleCookie
import shutil
import subprocess
import textwrap

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


def test_malformed_session_cookie_is_replaced(client):
    import app as app_module

    client.set_cookie(app_module.SESSION_COOKIE_NAME, "bad.session")
    response = client.get("/html-memory")
    cookie = SimpleCookie(response.headers["Set-Cookie"])

    assert app_module.SESSION_COOKIE_NAME in cookie
    assert cookie[app_module.SESSION_COOKIE_NAME].value == "badsession"


def test_empty_sanitized_session_cookie_is_regenerated(client):
    import app as app_module

    client.set_cookie(app_module.SESSION_COOKIE_NAME, ".")
    response = client.get("/html-memory")
    cookie = SimpleCookie(response.headers["Set-Cookie"])
    replacement = cookie[app_module.SESSION_COOKIE_NAME].value

    assert replacement
    assert replacement != "."


def test_ai_unavailable_matching_avoids_rate_false_positives():
    import app as app_module

    assert app_module._is_ai_unavailable("This is a great page with separate sections.") is False
    assert app_module._is_ai_unavailable("Iterate on the layout after preview.") is False
    assert app_module._is_ai_unavailable("The provider returned a rate limit error.") is True
    assert app_module._is_ai_unavailable("AI service not configured. Please set an API key.") is True


def test_flask_debug_is_env_driven(monkeypatch):
    import app as app_module

    monkeypatch.delenv("FLASK_DEBUG", raising=False)
    assert app_module._flask_debug_enabled() is False
    monkeypatch.setenv("FLASK_DEBUG", "true")
    assert app_module._flask_debug_enabled() is True
    monkeypatch.setenv("FLASK_DEBUG", "0")
    assert app_module._flask_debug_enabled() is False


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


def test_publish_site_serves_multiple_pages(client):
    response = client.post(
        "/publish-site",
        json={
            "pages": {
                "home": "<h1>Club Home</h1><a href='about.html'>About</a>",
                "about": "<h1>About Club</h1>",
                "contact": "<h1>Contact Club</h1>",
            }
        },
    )
    data = response.get_json()
    assert response.status_code == 200
    assert data["success"] is True
    assert data["pages"]["home"].endswith("/")
    assert data["pages"]["about"].endswith("/about.html")

    assert "Club Home" in client.get(data["pages"]["home"]).get_data(as_text=True)
    assert "About Club" in client.get(data["pages"]["about"]).get_data(as_text=True)
    assert "Contact Club" in client.get(data["pages"]["contact"]).get_data(as_text=True)


def test_student_site_serves_html_pages_only(client):
    response = client.post(
        "/publish-site",
        json={"pages": {"home": "<h1>Home</h1>", "about": "<h1>About</h1>"}},
    )
    data = response.get_json()

    assert client.get(data["pages"]["about"]).status_code == 200
    assert client.get(data["url"] + "style.css").status_code == 404
    assert client.get(data["url"] + "assets/app.js").status_code == 404
    assert client.get(data["url"] + "Home.html").status_code == 404


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


def test_reset_session_cannot_clear_another_session(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    import app as app_module

    monkeypatch.setattr(app_module, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    first_client = app_module.app.test_client()
    second_client = app_module.app.test_client()

    first_site = first_client.post("/publish-site", json={"html": "<h1>Keep Me</h1>"}).get_json()
    assert first_client.get(first_site["url"]).status_code == 200

    reset = second_client.post("/reset-session", json={"url": first_site["url"]}).get_json()
    assert reset["success"] is True
    assert first_client.get(first_site["url"]).status_code == 200


def test_html_audit_scores_accessibility(client):
    html = "<!doctype html><html lang='en'><head><title>Club</title><meta name='viewport' content='width=device-width'></head><body><main><h1>Club</h1><button>Join</button></main></body></html>"
    data = client.post("/html-audit", json={"html": html}).get_json()
    assert data["success"] is True
    assert data["audit"]["score"] >= 80
    assert data["audit"]["total"] == len(data["audit"]["checks"])
    assert data["audit"]["contrast_pairs"]
    assert data["audit"]["screen_reader_checks"]
    assert data["audit"]["screen_reader_transcript"]
    assert data["audit"]["screen_reader_transcript"][0]["announcement"].startswith("main")


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
    assert any(item["announcement"] == "button, unnamed" for item in data["audit"]["screen_reader_transcript"])


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


def test_generate_code_fallback_escapes_prompt_html(client):
    response = client.post(
        "/generate-code",
        json={"prompt": "Build a website for <script>alert(1)</script> club"},
    )
    data = response.get_json()
    assert response.status_code == 200
    assert data["success"] is True
    assert "<script>alert(1)</script>" not in data["code"]
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in data["code"]


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
    assert client.post("/voice-command", json={"text": "center the section text"}).get_json()["action"] == "edit_css"
    assert client.post("/voice-command", json={"text": "make the buttons rounded"}).get_json()["action"] == "edit_css"
    assert client.post("/voice-command", json={"text": "turn on high contrast"}).get_json()["action"] == "edit_css"
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


def test_frontend_uses_current_template_ids_only():
    script = open("static/codeup-html.js", encoding="utf-8").read()

    for legacy_id in (
        "voiceText",
        "command-input-label",
        "startGate",
        "structurePanel",
        "inputAddField",
        "tutorialBtn",
    ):
        assert legacy_id not in script


def test_voice_state_separates_wake_and_active_modes():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for the JS voice-state check")

    harness = textwrap.dedent(
        r"""
        const fs = require('fs');
        const vm = require('vm');

        function assert(condition, message) {
          if (!condition) throw new Error(message);
        }

        function makeElement(id) {
          const classes = new Set();
          return {
            id,
            textContent: '',
            attributes: {},
            classList: {
              toggle(name, enabled) {
                if (enabled) classes.add(name);
                else classes.delete(name);
              },
              contains(name) {
                return classes.has(name);
              },
            },
            setAttribute(name, value) {
              this.attributes[name] = String(value);
            },
            getAttribute(name) {
              return this.attributes[name];
            },
          };
        }

        const voiceButton = makeElement('voiceButton');
        const elements = {
          voiceButton,
          srAnnouncer: makeElement('srAnnouncer'),
          output: makeElement('output'),
          languageSelector: { value: 'en', addEventListener() {} },
        };
        const storage = new Map();
        const recognitions = [];

        class MockRecognition {
          constructor() {
            this.starts = 0;
            this.stops = 0;
            recognitions.push(this);
          }
          start() {
            this.starts += 1;
            if (this.onstart) this.onstart();
          }
          stop() {
            this.stops += 1;
            if (this.onend) this.onend();
          }
        }

        const context = {
          console,
          Date,
          setTimeout(callback) { callback(); },
          localStorage: {
            getItem(key) { return storage.get(key) || null; },
            setItem(key, value) { storage.set(key, String(value)); },
          },
          SpeechSynthesisUtterance: function SpeechSynthesisUtterance(text) {
            this.text = text;
          },
          document: {
            getElementById(id) { return elements[id] || null; },
            addEventListener() {},
            body: { dataset: {} },
          },
          window: {
            __codeupEnableTestHooks: true,
            SpeechRecognition: MockRecognition,
            webkitSpeechRecognition: MockRecognition,
            speechSynthesis: { cancel() {}, speak() {} },
            addEventListener() {},
          },
        };
        context.window.window = context.window;
        context.window.document = context.document;
        context.window.localStorage = context.localStorage;

        vm.runInNewContext(fs.readFileSync('static/codeup-html.js', 'utf8'), context);
        const api = context.window.__codeupVoiceTest;

        api.startWakeListener();
        assert(api.state.wakeListening === true, 'wake listener should be active');
        assert(api.state.activeVoice === false, 'passive wake should not enable active voice');
        assert(voiceButton.textContent === 'Voice Off', 'wake standby must not show Voice On');
        assert(voiceButton.getAttribute('aria-pressed') === 'false', 'wake standby must not press the voice button');
        const wake = recognitions[0];

        api.toggleVoice();
        assert(wake.stops === 1, 'starting active voice should stop passive wake recognition');
        assert(api.state.activeVoice === true, 'active voice should turn on');
        assert(api.state.wakeListening === false, 'passive wake should be suspended during active voice');
        assert(voiceButton.textContent === 'Voice On', 'active voice should show Voice On');
        const active = recognitions[1];

        api.pauseVoice();
        assert(api.state.activeVoice === true, 'pause should preserve active voice mode');
        assert(api.state.paused === true, 'pause should mark voice as paused');
        assert(active.stops === 1, 'pause should stop active recognition');
        assert(voiceButton.textContent === 'Voice Paused', 'pause should update the button label');
        assert(voiceButton.getAttribute('aria-pressed') === 'false', 'paused voice is not active listening');
        assert(api.state.wakeListening === true, 'pause should restart passive wake recognition for resume');
        const wakeWhilePaused = recognitions[2];

        api.resumeVoice();
        assert(wakeWhilePaused.stops === 1, 'resume should stop passive wake recognition');
        assert(api.state.activeVoice === true && api.state.paused === false, 'resume should restore active listening');
        assert(voiceButton.textContent === 'Voice On', 'resume should show Voice On');
        const resumed = recognitions[3];

        api.toggleVoice();
        assert(resumed.stops === 1, 'voice toggle should stop active recognition');
        assert(api.state.activeVoice === false, 'voice toggle should turn active mode off');
        assert(voiceButton.textContent === 'Voice Off', 'voice off should update the button label');
        """
    )

    subprocess.run([node, "-e", harness], check=True, cwd=".")
