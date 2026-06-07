import pytest

from codeup.services.web_learning import build_code_map, mistake_replay, validate_tutorial_step


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    import app as app_module
    import codeup.config as config_module

    monkeypatch.setattr(config_module, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


HTML = """<!doctype html>
<html lang="en">
<head><title>Robotics Lab</title><link rel="stylesheet" href="style.css"></head>
<body>
  <header class="hero"><h1>Robotics Lab</h1><button id="theme-toggle">Dark mode</button></header>
  <nav aria-label="Main navigation"><a href="#projects">Projects</a></nav>
  <main>
    <section id="projects" class="hero-card"><h2>Projects</h2><button class="filter">Filter</button></section>
    <form aria-label="Join form"><label for="name">Name</label><input id="name"></form>
    <img src="robot.png" alt="Student robot">
  </main>
  <footer><p>Contact the team</p></footer>
  <script src="script.js" defer></script>
</body>
</html>"""

CSS = """.hero { background: #101820; color: white; }
.hero-card { border-radius: 12px; }
button { background: #2563eb; color: white; }"""

JS = """function toggleTheme() {}
var themeButton = document.getElementById('theme-toggle');
if (themeButton) {
  themeButton.addEventListener('click', toggleTheme);
}"""


def test_tutorial_modules_route_and_validation(client):
    modules = client.get("/tutorial/modules").get_json()
    assert modules["success"] is True
    assert [item["id"] for item in modules["modules"]][:2] == ["html_basics", "structure"]

    valid = client.post(
        "/tutorial/validate", json={"module": "html_basics", "html": HTML, "css": CSS, "js": JS}
    ).get_json()
    assert valid["valid"] is True

    missing = validate_tutorial_step("structure", "<h1>Only heading</h1>", "", "")
    assert missing["valid"] is False
    assert "header" in missing["hint"]


def test_code_map_parser_and_natural_queries(client):
    data = client.post(
        "/code-map",
        json={"html": HTML, "css": CSS, "js": JS, "query": "what CSS styles the hero section"},
    ).get_json()

    assert data["success"] is True
    assert data["landmarks"]
    assert any(item["tag"] == "nav" for item in data["landmarks"])
    assert any(item["selector"] == ".hero" for item in data["css"])
    assert data["javascript"]["functions"][0]["name"] == "toggleTheme"
    assert "Hero CSS" in data["answer"]
    assert "line" in data["summary"]

    service_map = build_code_map(HTML, CSS, JS, "list all buttons")
    assert "Dark mode" in service_map["answer"]


def test_watchpoint_pause_rules(client):
    html = "<html><body><main><h1>Demo</h1><button></button><img src='x.png'></main></body></html>"
    data = client.post("/watchpoints/check", json={"html": html, "enabled": ["button_label"]}).get_json()

    assert data["paused"] is True
    assert data["issue"]["id"] == "unnamed_button"
    assert "Paused because" in data["reason"]


def test_mistake_replay_structural_diff(client):
    before = "<html><body><main><h1>Demo</h1><button></button></main></body></html>"
    after = "<html><body><main><h1>Demo</h1><section id='contact'><h2>Contact</h2></section><button>Send</button></main></body></html>"
    data = client.post("/mistake-replay", json={"html_before": before, "html_after": after}).get_json()

    assert data["success"] is True
    assert any("Added 1 <section>" in change for change in data["changes"])
    assert any("Accessibility issue fixed" in change for change in data["changes"])

    service = mistake_replay(
        before, after, ".hero { color: red; }", ".hero { color: red; background: blue; }", "", "function init() {}"
    )
    assert any("Changed CSS selector .hero" in change for change in service["changes"])
    assert any("Added JavaScript function init()" in change for change in service["changes"])


def test_beginner_error_explanations(client):
    data = client.post(
        "/explain-errors",
        json={
            "html": "<html><body><main><h1>Demo<button></button><img src='x.png'></main></body></html>",
            "css": ".missing { color: red; ",
            "js": "document.querySelector('#missing').addEventListener('click', function () {",
        },
    ).get_json()

    assert data["success"] is True
    assert any("CSS has unbalanced braces" in issue for issue in data["issues"])
    assert any("DOM query #missing" in issue for issue in data["issues"])
    assert any("Accessibility" in issue for issue in data["issues"])


def test_beginner_errors_ignore_generated_comments_and_dynamic_selectors(client):
    html = """<html><body>
    <button class="theme-toggle" data-theme-toggle>Dark</button>
    <button class="filter-btn" aria-pressed="true">Filter</button>
    <section class="card"></section>
    <p class="form-status" data-state="ok"></p>
    </body></html>"""
    css = """/* CodeUp-Web generated styles — responsive, accessible, no external assets */
    [data-theme="dark"] { color: white; }
    .card[hidden] { display: none; }
    .filter-btn[aria-pressed="true"] { border-color: currentColor; }
    .form-status[data-state="ok"] { color: green; }
    img, svg { max-width: 100%; }
    .missing-target { color: red; }"""
    js = """var themeButton = document.querySelector('[data-theme-toggle]');
    var filters = document.querySelectorAll('.filter-btn[aria-pressed="true"]');"""

    data = client.post("/explain-errors", json={"html": html, "css": css, "js": js}).get_json()

    assert data["success"] is True
    joined = "\n".join(data["issues"])
    assert "generated styles" not in joined
    assert "responsive" not in joined
    assert "[data-theme" not in joined
    assert "img" not in joined
    assert "data-theme-toggle" not in joined
    assert any(".missing-target" in issue for issue in data["issues"])


def test_new_voice_command_routes(client):
    expected = {
        "start tutorial": "tutorial_start",
        "continue": "tutorial_control",
        "what JavaScript controls the dark mode button": "code_map",
        "make the design dark mode": "darken_theme",
        "give me a code map": "code_map",
        "what CSS styles the hero section": "code_map",
        "what is inside the hero section": "code_map",
        "map this website": "code_map",
        "list all buttons": "code_map",
        "compare before and after": "review_changes",
        "compare accessibility before and after": "walkthrough_compare",
        "replay my mistake": "review_changes",
        "pause when image has no alt text": "walkthrough_pause_issues",
        "pause when an image has no alt text": "walkthrough_pause_issues",
        "where am I": "breadcrumb",
        "explain this error": "explain_errors",
        "explain simply": "explain_errors",
        "remember this as robotics hero": "save_macro",
        "use macro robotics hero": "run_macro",
        "bookmark this as hero section": "save_bookmark",
        "read from bookmark hero section": "read_bookmark",
        "restore my last work": "restore_work",
    }
    for command, action in expected.items():
        data = client.post("/voice-command", json={"text": command}).get_json()
        assert data["action"] == action, command

    bookmark = client.post("/voice-command", json={"text": "bookmark this as hero section"}).get_json()
    assert bookmark["slots"]["name"] == "hero section"

    watchpoint = client.post("/voice-command", json={"text": "pause when image has no alt text"}).get_json()
    assert watchpoint["slots"]["watchpoint"] == "image_alt"
