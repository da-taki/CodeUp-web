import platform
import socket
import threading
from pathlib import Path
from urllib.parse import urljoin

import pytest
from werkzeug.serving import make_server

playwright_api = pytest.importorskip("playwright.sync_api")


def _system_browser_paths() -> list[str]:
    system = platform.system()
    candidates: list[Path] = []
    if system == "Windows":
        candidates = [
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
            Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path.home() / r"AppData\Local\Microsoft\Edge\Application\msedge.exe",
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    else:
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
            Path("/snap/bin/chromium"),
            Path("/usr/bin/microsoft-edge"),
            Path("/usr/bin/microsoft-edge-stable"),
        ]
    return [str(p) for p in candidates if p.exists()]


def _launch_browser(p):
    options = {"headless": True}
    try:
        return p.chromium.launch(**options)
    except playwright_api.Error:
        pass
    for path in _system_browser_paths():
        try:
            return p.chromium.launch(headless=True, executable_path=path)
        except playwright_api.Error:
            continue
    pytest.skip("No Chromium-compatible browser available for E2E tests")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture()
def live_server(monkeypatch, tmp_path):
    monkeypatch.setenv("FLASK_TESTING", "true")
    monkeypatch.setenv("GEMINI_ENABLED", "0")
    import app as app_module
    import codeup.config as config_module

    monkeypatch.setattr(config_module, "DATA_DIR", str(tmp_path))
    app_module.app.config.update(TESTING=True)
    port = _free_port()
    server = make_server("127.0.0.1", port, app_module.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture()
def browser_page(live_server):
    with playwright_api.sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page(accept_downloads=True)
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.goto(live_server + "/", wait_until="networkidle")
        page.wait_for_selector("body[data-html-mode-ready='true']", timeout=15000)
        yield page, live_server, console_errors
        browser.close()


def run_command(page, text: str, marker: str):
    page.locator("#commandInput").fill(text)
    page.locator("#sendCommandBtn").click()
    page.wait_for_function(
        "marker => document.querySelector('#output').textContent.includes(marker)",
        arg=marker,
        timeout=15000,
    )


def click_more_action(page, action: str):
    page.locator("#moreBtn").click()
    page.locator(f"#moreMenu [data-action='{action}']").click()


class TestMinimalInterface:
    def test_initial_screen_is_ready_and_compact(self, browser_page):
        page, _, _ = browser_page
        assert page.locator("#htmlEditor").input_value().strip()
        assert page.locator("#cssEditor").input_value().strip()
        assert page.locator("#jsEditor").input_value().strip()
        assert page.locator("#stopBtn").is_hidden()
        assert page.locator("#moreOverlay").is_hidden()
        assert page.locator("#helpOverlay").is_hidden()
        assert page.locator("#sendCommandBtn, #runBtn, #voiceButton, #moreBtn, #settingsBtn, #helpBtn").count() == 6

    def test_file_tabs_show_content_immediately(self, browser_page):
        page, _, _ = browser_page
        page.locator("#cssEditor").evaluate("element => element.value = 'body { color: rgb(10, 20, 30); }'")
        page.locator("#jsEditor").evaluate("element => element.value = 'window.loadedNow = true;'")
        page.locator("#tabCss").click()
        assert "rgb(10, 20, 30)" in page.locator("#cssEditor").input_value()
        page.locator("#tabJs").click()
        assert "loadedNow" in page.locator("#jsEditor").input_value()
        page.locator("#tabHtml").click()
        assert "My CodeUp Website" in page.locator("#htmlEditor").input_value()


class TestWebsiteWorkflows:
    def test_generate_and_preview_site_with_source_assets(self, browser_page):
        page, live_server, _ = browser_page
        run_command(page, "make a website for my robotics club", "Your website is ready")
        assert "Robotics" in page.locator("#htmlEditor").input_value()
        assert page.locator("#cssEditor").input_value().strip()
        assert page.locator("#jsEditor").input_value().strip()
        page.locator("#runBtn").click()
        page.wait_for_selector("#sitePreviewFrame[src]", timeout=10000)
        src = page.locator("#sitePreviewFrame").get_attribute("src")
        absolute = urljoin(live_server, src)
        css = page.request.get(urljoin(absolute, "style.css"))
        script = page.request.get(urljoin(absolute, "script.js"))
        assert css.ok
        assert script.ok
        assert "body" in css.text()
        assert script.text().strip()

    def test_more_menu_audit_fix_and_run_commands(self, browser_page):
        page, _, _ = browser_page
        page.locator("#htmlEditor").fill(
            "<html><head><title></title></head><body><img src='hero.png'><button></button></body></html>"
        )
        click_more_action(page, "check-accessibility")
        page.wait_for_function("() => document.querySelector('#output').textContent.includes('Accessibility score')")
        click_more_action(page, "fix-accessibility")
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('Applied safe accessibility fixes')"
        )
        assert "Describe this image" in page.locator("#htmlEditor").input_value()
        click_more_action(page, "run-website")
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('WEBSITE RUNTIME TEACHER')"
        )

    def test_save_open_and_export_project(self, browser_page):
        page, _, _ = browser_page
        page.locator("#htmlEditor").fill(
            "<!doctype html><html lang='en'><head><title>Saved</title></head><body><h1>Saved Marker</h1></body></html>"
        )
        page.locator("#tabCss").click()
        page.locator("#cssEditor").fill("body { background: rgb(240, 240, 240); }")
        page.locator("#tabJs").click()
        page.locator("#jsEditor").fill("window.savedMarker = true;")
        page.locator("#tabHtml").click()
        page.locator("#projectNameInput").evaluate("element => element.value = 'E2E Saved Site'")
        click_more_action(page, "save-project")
        page.wait_for_function("() => document.querySelector('#output').textContent.includes('Saved E2E Saved Site')")
        page.locator("#htmlEditor").fill("<h1>Changed</h1>")
        click_more_action(page, "open-project")
        page.locator("#projectOpenBtn").click()
        page.wait_for_function("() => document.querySelector('#htmlEditor').value.includes('Saved Marker')")
        assert "rgb(240, 240, 240)" in page.locator("#cssEditor").input_value()
        assert "savedMarker" in page.locator("#jsEditor").input_value()
        page.keyboard.press("Escape")
        assert page.locator("#projectOverlay").is_hidden()
        with page.expect_response(lambda response: response.url.endswith("/export-site.zip") and response.ok):
            click_more_action(page, "export-zip")
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('Exported the website ZIP')"
        )


class TestHelpSettingsKeyboard:
    @pytest.mark.parametrize("alias", ["help", "what can I do here", "list of commands", "show commands", "commands"])
    def test_help_aliases_open_same_panel(self, browser_page, alias):
        page, _, _ = browser_page
        run_command(page, alias, "Help is open")
        assert page.locator("#helpOverlay").is_visible()
        assert page.locator("#helpCommandList").text_content().count("Build") == 1
        page.keyboard.press("Escape")
        assert page.locator("#helpOverlay").is_hidden()

    def test_settings_persist_and_escape_closes(self, browser_page):
        page, _, _ = browser_page
        page.locator("#settingsBtn").click()
        page.locator("#nightToggle").check()
        page.locator("#dyslexiaToggle").check()
        assert page.locator("body.night-mode.dyslexia-mode").count() == 1
        stored = page.evaluate("() => localStorage.getItem('codeup_settings')")
        assert "nightToggle" in stored
        page.keyboard.press("Escape")
        assert page.locator("#settingsOverlay").is_hidden()

    def test_enter_ctrl_enter_and_mobile_preview(self, browser_page):
        page, _, _ = browser_page
        page.locator("#commandInput").fill("check accessibility")
        page.keyboard.press("Enter")
        page.wait_for_function("() => document.querySelector('#output').textContent.includes('Accessibility score')")
        page.locator("#previewMobileBtn").click()
        assert page.locator("#sitePreview").get_attribute("data-size") == "mobile"
        page.locator("#htmlEditor").focus()
        page.keyboard.press("Control+Enter")
        page.wait_for_selector("#sitePreviewFrame[src]", timeout=10000)


class TestConsoleErrors:
    def test_no_unexpected_js_errors(self, browser_page):
        page, _, console_errors = browser_page
        page.locator("#runBtn").click()
        page.wait_for_selector("#sitePreviewFrame[src]", timeout=10000)
        ignored = ("speechSynthesis", "SpeechRecognition", "favicon.ico", "404 (NOT FOUND)")
        unexpected = [e for e in console_errors if not any(s in e for s in ignored)]
        assert unexpected == [], f"Unexpected JS console errors: {unexpected}"
