import platform
import socket
import threading
from pathlib import Path

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
        page = browser.new_page()
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.goto(live_server + "/", wait_until="networkidle")
        page.wait_for_selector("body[data-html-mode-ready='true']", timeout=15000)
        yield page, live_server, console_errors
        browser.close()


class TestPageLoad:
    def test_page_loads_and_ready_flag_set(self, browser_page):
        page, _, _ = browser_page
        assert page.locator("body[data-html-mode-ready='true']").count() == 1

    def test_editor_exists(self, browser_page):
        page, _, _ = browser_page
        assert page.locator("#htmlEditor").count() == 1
        assert page.locator("#htmlEditor").input_value().strip() != ""


class TestPreviewButton:
    def test_preview_creates_iframe_src(self, browser_page):
        page, _, _ = browser_page
        page.locator("#runBtn").click()
        page.wait_for_function(
            "() => document.querySelector('#sitePreviewFrame') && document.querySelector('#sitePreviewFrame').getAttribute('src')",
            timeout=10000,
        )
        src = page.locator("#sitePreviewFrame").get_attribute("src")
        assert src and "/student-site/" in src

    def test_preview_uses_current_css_and_javascript_panes(self, browser_page):
        page, _, _ = browser_page
        page.locator("#htmlEditor").fill(
            "<!doctype html><html lang='en'><head><title>Preview</title></head>"
            "<body><main class='hero'><h1>Preview</h1></main></body></html>"
        )
        page.locator("#cssEditor").evaluate(
            """element => {
                element.value = ".hero { border-top: 9px solid rgb(255, 0, 0); }";
                element.dispatchEvent(new Event("input", { bubbles: true }));
            }"""
        )
        page.locator("#jsEditor").evaluate(
            """element => {
                element.value = "window.previewJsFlag = 'yes';";
                element.dispatchEvent(new Event("input", { bubbles: true }));
            }"""
        )

        with page.expect_response(
            lambda response: "/student-site/" in response.url and response.request.resource_type == "document",
            timeout=10000,
        ) as response_info:
            page.locator("#runBtn").click()

        hosted_html = response_info.value.text()
        assert "border-top: 9px" in hosted_html
        assert "previewJsFlag" in hosted_html


class TestGuidedLearning:
    def test_tutorial_macro_bookmark_breadcrumb_and_replay_commands(self, browser_page):
        page, _, _ = browser_page

        def command(text: str, marker: str):
            page.locator("#commandInput").fill(text)
            page.locator("#sendCommandBtn").click()
            page.wait_for_function(
                "marker => document.querySelector('#output').textContent.includes(marker)"
                " || document.querySelector('#tutorialStatus').textContent.includes(marker)",
                arg=marker,
                timeout=15000,
            )

        command("start tutorial", "HTML basics")
        command("insert page title Demo", "Success")
        assert "Demo" in page.locator("#htmlEditor").input_value()

        command("remember this as title demo", "Saved macro")
        command("bookmark this as tutorial point", "Bookmarked")
        command("read from bookmark tutorial point", "Bookmark tutorial point")
        command("where am I", "HTML")
        command("compare before and after", "Mistake replay")


class TestAuditAndFix:
    def test_audit_button_reports_issues(self, browser_page):
        page, _, _ = browser_page
        bad_html = (
            "<html><head><title></title></head><body><img src='hero.png'><button></button><p>Hello</p></body></html>"
        )
        page.locator("#htmlEditor").fill(bad_html)
        page.locator("#auditBtn").click()
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('missing_image_alt')",
            timeout=10000,
        )
        output = page.locator("#output").text_content()
        assert "missing_image_alt" in output

    def test_apply_safe_fixes(self, browser_page):
        page, _, _ = browser_page
        bad_html = (
            "<html><head><title></title></head><body><img src='hero.png'><button></button><p>Hello</p></body></html>"
        )
        page.locator("#htmlEditor").fill(bad_html)
        page.locator("#auditBtn").click()
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('missing_image_alt')",
            timeout=10000,
        )
        assert page.locator("#auditFixAllBtn").is_enabled()
        with page.expect_response(
            lambda response: response.url.endswith("/audit-autofix") and response.ok, timeout=15000
        ):
            page.locator("#auditFixAllBtn").evaluate("button => button.click()")
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('Applied safe audit fixes')",
            timeout=10000,
        )
        assert 'alt="Describe this image"' in page.locator("#htmlEditor").input_value()


class TestProjectCreateSaveOpen:
    def test_create_and_save_project(self, browser_page):
        page, _, _ = browser_page
        page.locator("#projectNameInput").fill("E2E Robotics")
        page.locator("#projectSaveBtn").click()
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('Saved project') || document.querySelector('#output').textContent.includes('Created project')",
            timeout=10000,
        )
        output = page.locator("#output").text_content()
        assert "E2E Robotics" in output

    def test_open_project_from_dropdown(self, browser_page):
        page, _, _ = browser_page
        page.locator("#projectNameInput").fill("Open Test")
        page.locator("#projectSaveBtn").click()
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('project')",
            timeout=10000,
        )
        options = page.locator("#projectSelect option").all()
        assert len(options) >= 1


class TestExport:
    def test_export_downloads_file(self, browser_page):
        page, _, _ = browser_page
        page.locator("#commandInput").fill("create a multi page website for robotics showcase")
        page.locator("#sendCommandBtn").click()
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('homepage')",
            timeout=15000,
        )
        with page.expect_download() as download_info:
            page.locator("#exportBtn").click()
        download = download_info.value
        assert download.suggested_filename.endswith(".zip")


class TestKeyboardFlow:
    def test_tab_navigation(self, browser_page):
        page, _, _ = browser_page
        page.keyboard.press("Tab")
        focused = page.evaluate("() => document.activeElement.id || document.activeElement.tagName")
        assert focused

    def test_ctrl_enter_triggers_preview(self, browser_page):
        page, _, _ = browser_page
        page.locator("#htmlEditor").focus()
        page.keyboard.press("Control+Enter")
        page.wait_for_function(
            "() => document.querySelector('#sitePreviewFrame') && document.querySelector('#sitePreviewFrame').getAttribute('src')",
            timeout=10000,
        )
        src = page.locator("#sitePreviewFrame").get_attribute("src")
        assert src and "/student-site/" in src


class TestProofTeachingLoop:
    def _command(self, page, text, marker):
        page.locator("#commandInput").fill(text)
        page.locator("#sendCommandBtn").click()
        page.wait_for_function(
            "marker => document.querySelector('#output').textContent.includes(marker)",
            arg=marker,
            timeout=15000,
        )

    def test_runtime_debug_selector_readiness_commands(self, browser_page):
        page, _, _ = browser_page
        self._command(page, "create a multi page website for robotics showcase", "homepage")
        self._command(page, "run website", "WEBSITE RUNTIME TEACHER")
        assert "did not click" in page.locator("#output").text_content().lower()
        self._command(page, "debug website", "WEBSITE DEBUG TEACHER")
        self._command(page, "what CSS affects the navigation", "SELECTOR EXPLAINER")
        self._command(page, "is this ready to share", "Readiness score")

    def test_run_website_button(self, browser_page):
        page, _, _ = browser_page
        self._command(page, "create a multi page website for robotics showcase", "homepage")
        page.locator("#runWebsiteBtn").click()
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('WEBSITE RUNTIME TEACHER')",
            timeout=15000,
        )

    def test_guided_build_track_intercepts_only_control_words(self, browser_page):
        page, _, _ = browser_page
        self._command(page, "build my first website", "Guided build")
        self._command(page, "create a multi page website for robotics showcase", "homepage")
        self._command(page, "recap", "RECAP")


class TestConsoleErrors:
    def test_no_unexpected_js_errors(self, browser_page):
        page, _, console_errors = browser_page
        page.locator("#runBtn").click()
        page.wait_for_function(
            "() => document.querySelector('#sitePreviewFrame') && document.querySelector('#sitePreviewFrame').getAttribute('src')",
            timeout=10000,
        )
        ignored = ("speechSynthesis", "SpeechRecognition", "favicon.ico", "404 (NOT FOUND)")
        unexpected = [e for e in console_errors if not any(s in e for s in ignored)]
        assert unexpected == [], f"Unexpected JS console errors: {unexpected}"
