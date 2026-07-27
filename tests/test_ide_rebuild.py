import io
import json
import shutil
import subprocess
import textwrap
import zipfile

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
        "data-count",
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


def test_frontend_snippets_stop_speaking_and_code_map_behaviour():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for the frontend IDE harness")

    harness = textwrap.dedent(
        r"""
        const fs = require('fs');
        const vm = require('vm');

        function assert(condition, message) {
          if (!condition) throw new Error(message);
        }

        function makeElement(id) {
          return {
            id,
            value: '',
            textContent: '',
            innerHTML: '',
            dataset: {},
            children: [],
            attributes: {},
            disabled: false,
            classList: { toggle() {}, add() {}, remove() {} },
            appendChild(child) { this.children.push(child); return child; },
            setAttribute(name, value) { this.attributes[name] = String(value); },
            getAttribute(name) { return this.attributes[name]; },
            removeAttribute(name) { delete this.attributes[name]; },
            addEventListener() {},
            focus() {},
          };
        }

        function plainText(value) {
          return String(value || '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
        }

        class FakeHeading {
          constructor(tag, text) {
            this.tagName = tag.toUpperCase();
            this.textContent = plainText(text);
          }
        }

        class FakeNode {
          constructor(tag, attrs, html) {
            this.tagName = tag.toUpperCase();
            this.attrs = attrs || '';
            this.html = html || '';
          }
          querySelector() {
            const match = this.html.match(/<(h[1-3])\b[^>]*>([\s\S]*?)<\/\1>/i);
            return match ? new FakeHeading(match[1], match[2]) : null;
          }
          getAttribute(name) {
            const re = new RegExp(name + '=["\\\']([^"\\\']+)["\\\']', 'i');
            const match = this.attrs.match(re);
            return match ? match[1] : null;
          }
        }

        class FakeDocument {
          constructor(html) {
            this.html = html;
            this.body = this;
          }
          querySelectorAll(selector) {
            if (selector.startsWith('header,nav')) {
              const nodes = [];
              const re = /<(header|nav|main|section|article|aside|footer|form)\b([^>]*)>([\s\S]*?)<\/\1>/gi;
              let match;
              while ((match = re.exec(this.html))) nodes.push(new FakeNode(match[1], match[2], match[3]));
              return nodes;
            }
            if (selector.startsWith('h1,h2')) {
              const nodes = [];
              const re = /<(h[1-6])\b[^>]*>([\s\S]*?)<\/\1>/gi;
              let match;
              while ((match = re.exec(this.html))) nodes.push(new FakeHeading(match[1], match[2]));
              return nodes;
            }
            return [];
          }
        }

        const storage = new Map();
        const elements = {
          htmlEditor: makeElement('htmlEditor'),
          cssEditor: makeElement('cssEditor'),
          jsEditor: makeElement('jsEditor'),
          output: makeElement('output'),
          srAnnouncer: makeElement('srAnnouncer'),
          languageSelector: Object.assign(makeElement('languageSelector'), { value: 'en' }),
          snippetSelect: makeElement('snippetSelect'),
          tabHtml: makeElement('tabHtml'),
          tabCss: makeElement('tabCss'),
          tabJs: makeElement('tabJs'),
          panelHtml: makeElement('panelHtml'),
          panelCss: makeElement('panelCss'),
          panelJs: makeElement('panelJs'),
        };
        let cancelCount = 0;
        const context = {
          console,
          Date,
          setTimeout(callback) { callback(); return 1; },
          clearTimeout() {},
          DOMParser: class DOMParser { parseFromString(html) { return new FakeDocument(html); } },
          SpeechSynthesisUtterance: function SpeechSynthesisUtterance(text) { this.text = text; },
          sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
          localStorage: {
            getItem(key) { return storage.has(key) ? storage.get(key) : null; },
            setItem(key, value) { storage.set(key, String(value)); },
          },
          document: {
            activeElement: { id: '' },
            getElementById(id) { return elements[id] || null; },
            querySelector() { return null; },
            createElement(tag) { return makeElement(tag); },
            addEventListener() {},
            body: { dataset: {}, classList: { toggle() {}, remove() {}, add() {} } },
          },
          window: {
            __codeupEnableTestHooks: true,
            speechSynthesis: { cancel() { cancelCount += 1; }, speak() {} },
            addEventListener() {},
          },
        };
        context.window.window = context.window;
        context.window.document = context.document;
        context.window.sessionStorage = context.sessionStorage;
        context.window.localStorage = context.localStorage;
        context.window.DOMParser = context.DOMParser;

        vm.runInNewContext(fs.readFileSync('static/codeup-html.js', 'utf8'), context);
        const api = context.window.__codeupVoiceTest;

        api.loadGeneratedFiles({
          html: '<!doctype html><html lang="en"><head><title>Bakery</title><link rel="stylesheet" href="style.css"></head><body><header><h1>Bakery</h1></header><main><section><h2>Menu</h2><p>Cakes</p></section></main><script src="script.js" defer></script></body></html>',
          css: 'body { color: #111827; } .card { padding: 1rem; }',
          js: 'function initMenu() {} document.addEventListener("click", initMenu);',
        });
        const combined = api.getHtml();
        assert(combined.includes('id="codeup-ide-css"'), 'preview HTML should inline CSS');
        assert(combined.includes('id="codeup-ide-js"'), 'preview HTML should inline JS');
        assert(!combined.includes('href="style.css"'), 'preview HTML should not rely on sibling CSS');
        assert(!combined.includes('src="script.js"'), 'preview HTML should not rely on sibling JS');

        const split = api.splitDocument(combined);
        assert(split.html.includes('href="style.css"'), 'split HTML should keep style.css reference');
        assert(split.html.includes('src="script.js"'), 'split HTML should keep script.js reference');
        assert(split.css.includes('.card'), 'split CSS should return CSS pane content');
        assert(split.js.includes('initMenu'), 'split JS should return JS pane content');

        api.handleIdeCommand('make it more futuristic', 'make it more futuristic');
        assert(api.getCss().includes('#05060f'), 'design commands should append CSS to the CSS pane');
        assert(!elements.htmlEditor.value.includes('data-codeup-voice-css'), 'design commands should not hide CSS in index.html');

        api.saveSnippet('bakery demo');
        assert(JSON.parse(storage.get('codeup_snippets'))['bakery demo'], 'snippet should save with exact name');
        api.loadGeneratedFiles({ html: '<h1>Other</h1>', css: '', js: '' });
        api.loadSnippet('bakery demo');
        assert(api.getCss().includes('.card'), 'snippet load should restore CSS');
        assert(api.getJs().includes('initMenu'), 'snippet load should restore JS');
        api.deleteSnippet('bakery demo');
        assert(!JSON.parse(storage.get('codeup_snippets'))['bakery demo'], 'snippet should delete');

        (async () => {
          await api.codeMap();
          assert(elements.output.textContent.includes('HTML sections:'), 'code map should describe HTML');
          assert(elements.output.textContent.includes('CSS selectors:'), 'code map should describe CSS');
          assert(elements.output.textContent.includes('JavaScript events:'), 'code map should describe JS events');

          api.stopEverything();
          assert(cancelCount > 0, 'stop everything should cancel speech synthesis');
          assert(elements.output.textContent.includes('Stopped speaking'), 'stop everything should update visible output');
        })().catch((error) => {
          console.error(error);
          process.exit(1);
        });
        """
    )

    subprocess.run([node, "-e", harness], check=True, cwd=".")


def test_frontend_tutorial_macros_bookmarks_breadcrumbs_and_heartbeat():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required for the frontend IDE harness")

    harness = textwrap.dedent(
        r"""
        const fs = require('fs');
        const vm = require('vm');

        function assert(condition, message) {
          if (!condition) throw new Error(message);
        }

        function makeElement(id) {
          return {
            id,
            value: '',
            textContent: '',
            innerHTML: '',
            dataset: {},
            children: [],
            attributes: {},
            disabled: false,
            selectionStart: 0,
            selectionEnd: 0,
            classList: { toggle() { return false; }, add() {}, remove() {}, contains() { return false; } },
            appendChild(child) { this.children.push(child); return child; },
            setAttribute(name, value) { this.attributes[name] = String(value); },
            getAttribute(name) { return this.attributes[name]; },
            removeAttribute(name) { delete this.attributes[name]; },
            addEventListener() {},
            focus() {},
          };
        }

        const storage = new Map();
        const elements = {
          htmlEditor: makeElement('htmlEditor'),
          cssEditor: makeElement('cssEditor'),
          jsEditor: makeElement('jsEditor'),
          output: makeElement('output'),
          srAnnouncer: makeElement('srAnnouncer'),
          languageSelector: Object.assign(makeElement('languageSelector'), { value: 'en' }),
          tutorialPanel: makeElement('tutorialPanel'),
          tutorialStatus: makeElement('tutorialStatus'),
          tabHtml: makeElement('tabHtml'),
          tabCss: makeElement('tabCss'),
          tabJs: makeElement('tabJs'),
          panelHtml: makeElement('panelHtml'),
          panelCss: makeElement('panelCss'),
          panelJs: makeElement('panelJs'),
        };
        let cancelCount = 0;
        let intervalCallback = null;
        let delayedCodeMapResolve = null;
        let useDelayedCodeMap = false;
        const modules = [
          { id: 'html_basics', title: 'HTML basics', explanation: 'Explain HTML.', command: 'insert page title Demo', hint: 'Add title heading paragraph.' },
          { id: 'structure', title: 'Structure', explanation: 'Explain structure.', command: 'insert header nav main section footer', hint: 'Add landmarks.' },
        ];
        const context = {
          console,
          Date,
          setTimeout(callback) { callback(); return 1; },
          clearTimeout() {},
          setInterval(callback) { intervalCallback = callback; return 42; },
          clearInterval(id) { if (id === 42) intervalCallback = null; },
          DOMParser: class DOMParser { parseFromString() { return { body: { querySelectorAll() { return []; } }, querySelectorAll() { return []; } }; } },
          SpeechSynthesisUtterance: function SpeechSynthesisUtterance(text) { this.text = text; },
          fetch: async function fetch(url, options) {
            const body = options && options.body ? JSON.parse(options.body) : {};
            if (url === '/tutorial/modules') return { json: async () => ({ success: true, modules }) };
            if (url === '/tutorial/validate') return { json: async () => ({ success: true, valid: body.html.includes('<title>Demo</title>'), message: 'Success. HTML basics is complete.', hint: 'Add title heading paragraph.' }) };
            if (url === '/voice-command') return { json: async () => ({ success: true, action: 'chat', slots: {}, confidence: 0.35 }) };
            if (url === '/code-map' && useDelayedCodeMap) {
              return new Promise((resolve) => {
                delayedCodeMapResolve = () => resolve({ json: async () => ({ success: true, summary: 'Stale code map response.', answer: 'Stale code map response.' }) });
              });
            }
            if (url === '/code-map') return { json: async () => ({ success: true, summary: 'Dark mode JavaScript: line 8 [data-theme-toggle].', answer: 'Dark mode JavaScript: line 8 [data-theme-toggle].' }) };
            if (url === '/mistake-replay') return { json: async () => ({ success: true, message: 'Mistake replay:\n- Added HTML line: <title>Demo</title>', changes: ['Added HTML line'] }) };
            if (url === '/watchpoints/check') return { json: async () => ({ success: true, paused: true, reason: 'Paused because an image has no alt text.', issue: { id: 'missing_image_alt' } }) };
            return { json: async () => ({ success: true }) };
          },
          sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
          localStorage: {
            getItem(key) { return storage.has(key) ? storage.get(key) : null; },
            setItem(key, value) { storage.set(key, String(value)); },
            removeItem(key) { storage.delete(key); },
          },
          document: {
            activeElement: { id: '' },
            getElementById(id) { return elements[id] || null; },
            querySelector() { return null; },
            createElement(tag) { return makeElement(tag); },
            addEventListener() {},
            body: { dataset: {}, classList: { toggle() { return false; }, remove() {}, add() {}, contains() { return false; } } },
          },
          window: {
            __codeupEnableTestHooks: true,
            speechSynthesis: { speaking: false, cancel() { cancelCount += 1; }, speak() {} },
            addEventListener() {},
          },
        };
        context.window.window = context.window;
        context.window.document = context.document;
        context.window.sessionStorage = context.sessionStorage;
        context.window.localStorage = context.localStorage;
        context.window.DOMParser = context.DOMParser;

        vm.runInNewContext(fs.readFileSync('static/codeup-html.js', 'utf8'), context);
        const api = context.window.__codeupVoiceTest;

        (async () => {
          api.loadGeneratedFiles({ html: '<!doctype html><html lang="en"><head><title>Old</title><link rel="stylesheet" href="style.css"></head><body><h1>Old</h1><p>Start</p><script src="script.js" defer></script></body></html>', css: '', js: '' });
          await api.handleTutorialCommand('start tutorial');
          assert(api.state.tutorial.active, 'tutorial should become active');
          await api.handleStudentText('insert page title Demo');
          assert(api.getHtml().includes('<title>Demo</title>'), 'tutorial exercise should route through normal command parser');
          assert(elements.tutorialStatus.textContent.includes('Success'), 'tutorial should validate after normal command');

          api.state.lastCommand = 'insert page title Macro Demo';
          await api.saveMacro('remember this as title macro');
          assert(JSON.parse(storage.get('codeup_voice_macros'))['title macro'], 'macro should save last command');
          await api.runMacro('use macro title macro');
          assert(api.getHtml().includes('<title>Macro Demo</title>'), 'macro should replay website command');

          api.saveBookmark('bookmark this as hero section');
          assert(JSON.parse(storage.get('codeup_bookmarks'))['hero section'], 'bookmark should persist');
          api.readBookmark('read from bookmark hero section');
          assert(elements.output.textContent.includes('Bookmark hero section'), 'bookmark should read');

          api.state.watchpointRules = ['image_alt'];
          elements.output.textContent = 'Accessibility score: 80/100';
          await api.checkWatchpoints('Audit');
          assert(elements.output.textContent.includes('Accessibility score: 80/100'), 'watchpoint should preserve current audit output');
          assert(elements.output.textContent.includes('Paused because an image has no alt text'), 'watchpoint should append pause reason');

          api.state.walkthrough.htmlBeforeFix = '';
          api.state.replay.before = { html: '<button></button>', css: '', js: '' };
          api.state.replay.after = { html: '<button>Send</button>', css: '', js: '' };
          await api.walkthroughCompare();
          assert(elements.output.textContent.includes('Accessibility comparison'), 'accessibility compare should fall back to replay after main fix');

          api.loadGeneratedFiles({ html: '<main><h1>Theme demo</h1><button data-theme-toggle>Dark</button></main>', css: '', js: 'var themeBtn = document.querySelector("[data-theme-toggle]");' });
          api.state.lastCommand = 'make the design futuristic with dark mode and animated stats';
          api.handleIdeCommand('what JavaScript controls the dark mode button', 'what javascript controls the dark mode button');
          for (let i = 0; i < 8; i += 1) await Promise.resolve();
          assert(elements.output.textContent.includes('Dark mode JavaScript'), 'dark-mode code map query should not become a CSS edit');
          assert(!api.getCss().includes('background: #111827'), 'dark-mode code map query should not edit CSS');
          await api.handleStudentText('what JavaScript controls the dark mode button');
          for (let i = 0; i < 8; i += 1) await Promise.resolve();
          assert(api.state.lastCommand === 'make the design futuristic with dark mode and animated stats', 'code-map questions should not replace macro command memory');

          elements.htmlEditor.selectionStart = api.getHtml().indexOf('<h1>');
          elements.htmlEditor.selectionEnd = elements.htmlEditor.selectionStart;
          api.activateTab('html');
          api.breadcrumb();
          assert(elements.output.textContent.includes('HTML'), 'breadcrumb should describe HTML context');

          api.startHeartbeat('Testing heartbeat');
          assert(api.state.heartbeatTimer, 'heartbeat should start');
          api.stopEverything();
          assert(!api.state.heartbeatTimer, 'stop everything should cancel heartbeat');
          assert(cancelCount > 0, 'stop everything should cancel speech');

          useDelayedCodeMap = true;
          const staleMap = api.codeMap('give me a code map');
          await Promise.resolve();
          api.stopEverything();
          delayedCodeMapResolve();
          await staleMap;
          assert(elements.output.textContent.includes('Stopped speaking'), 'stop everything should keep stopped output');
          assert(!elements.output.textContent.includes('Stale code map response'), 'stale code map response should not overwrite output');
        })().catch((error) => {
          console.error(error);
          process.exit(1);
        });
        """
    )

    subprocess.run([node, "-e", harness], check=True, cwd=".")
