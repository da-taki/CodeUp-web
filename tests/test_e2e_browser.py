import socket
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

playwright_api = pytest.importorskip("playwright.sync_api")


def _system_browser_path() -> str | None:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path.home() / r"AppData\Local\Microsoft\Edge\Application\msedge.exe",
    ]
    for path in candidates:
        if path.exists():
            return str(path)
    return None


def _launch_browser(p):
    options = {"headless": True}
    executable_path = _system_browser_path()
    if executable_path:
        options["executable_path"] = executable_path
    try:
        return p.chromium.launch(**options)
    except playwright_api.Error as exc:
        pytest.skip(f"Chromium is not available for Playwright E2E: {exc}")


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


def test_browser_project_audit_autofix_export_and_keyboard_flow(live_server):
    with playwright_api.sync_playwright() as p:
        browser = _launch_browser(p)
        page = browser.new_page()
        page.goto(live_server + "/", wait_until="networkidle")
        page.wait_for_selector("body[data-html-mode-ready='true']")

        page.locator("#projectNameInput").fill("E2E Robotics")
        page.locator("#projectSaveBtn").click()
        page.wait_for_function("() => document.querySelector('#output').textContent.includes('Saved project')")

        bad_html = (
            "<html><head><title></title></head><body><img src='hero.png'><button></button><p>Hello</p></body></html>"
        )
        page.locator("#htmlEditor").fill(bad_html)
        page.locator("#auditBtn").click()
        page.wait_for_function("() => document.querySelector('#output').textContent.includes('missing_image_alt')")
        assert page.locator("#auditFixAllBtn").is_enabled()

        page.locator("#auditFixAllBtn").click()
        page.wait_for_function(
            "() => document.querySelector('#output').textContent.includes('Applied safe audit fixes')"
        )
        assert 'alt="Describe this image"' in page.locator("#htmlEditor").input_value()

        page.locator("#commandInput").fill("create a multi page website for robotics showcase")
        page.locator("#sendCommandBtn").click()
        page.wait_for_function("() => document.querySelector('#output').textContent.includes('homepage')")

        with page.expect_download() as download_info:
            page.locator("#exportBtn").click()
        download = download_info.value
        assert download.suggested_filename.endswith(".zip")

        page.keyboard.press("Tab")
        focused = page.evaluate("() => document.activeElement.id || document.activeElement.tagName")
        assert focused
        page.locator("#htmlEditor").focus()
        page.keyboard.press("Control+Enter")
        page.wait_for_function("() => document.querySelector('#sitePreviewFrame').getAttribute('src')")

        browser.close()
