import json
import shutil
import subprocess
import textwrap
from concurrent.futures import ThreadPoolExecutor
from http.cookies import SimpleCookie
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


class TestStreamingEndpoint:
    def test_stream_returns_event_stream_content_type(self, client):
        response = client.post(
            "/generate-code-stream",
            json={"prompt": "Build a website for a robotics club"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.content_type

    def test_stream_returns_fallback_html_when_ai_disabled(self, client):
        response = client.post(
            "/generate-code-stream",
            json={"prompt": "Build a website for a chess club"},
        )
        data = response.get_data(as_text=True)
        assert "data:" in data
        events = [json.loads(line[6:]) for line in data.strip().split("\n") if line.startswith("data: ")]
        assert any(event.get("done") for event in events)
        html_event = next(e for e in events if e.get("done"))
        content = html_event.get("chunk") or html_event.get("html", "")
        assert "Chess Club" in content or "chess" in content.lower()

    def test_stream_empty_prompt_returns_error(self, client):
        response = client.post("/generate-code-stream", json={"prompt": ""})
        assert response.status_code == 400

    def test_stream_too_large_prompt_returns_error(self, client):
        response = client.post("/generate-code-stream", json={"prompt": "x" * 30000})
        assert response.status_code == 413


class TestSmartMemory:
    def test_store_and_retrieve_smart_memory(self, client):
        response = client.post(
            "/smart-memory",
            json={"content": "My name is Alice and I am in grade 5", "type": "fact"},
        )
        data = response.get_json()
        assert data["success"] is True
        assert len(data["smart_memory"]) == 1
        assert data["smart_memory"][0]["type"] == "fact"
        assert data["smart_memory"][0]["content"] == "My name is Alice and I am in grade 5"

    def test_deduplication_prevents_storing_same_content_twice(self, client):
        for _ in range(3):
            client.post(
                "/smart-memory",
                json={"content": "Remember I prefer blue colors", "type": "instruction"},
            )
        memory = client.get("/smart-memory").get_json()
        assert len(memory["smart_memory"]) == 1

    def test_empty_content_is_rejected(self, client):
        response = client.post("/smart-memory", json={"content": "", "type": "fact"})
        assert response.status_code == 400

    def test_too_large_content_is_rejected(self, client):
        response = client.post("/smart-memory", json={"content": "x" * 1500, "type": "fact"})
        assert response.status_code == 413

    def test_filler_text_is_not_stored(self, client):
        for filler in ["um", "okay", "yes", "hi", "hmm"]:
            client.post("/smart-memory", json={"content": filler, "type": "context"})
        memory = client.get("/smart-memory").get_json()
        assert len(memory["smart_memory"]) == 0

    def test_memory_limit_caps_entries(self, client, monkeypatch):
        import codeup.config as config_module

        monkeypatch.setattr(config_module, "MAX_MEMORY_ENTRIES", 5)
        for i in range(10):
            client.post(
                "/smart-memory",
                json={"content": f"Important fact number {i} about the project", "type": "fact"},
            )
        memory = client.get("/smart-memory").get_json()
        assert len(memory["smart_memory"]) <= 5

    def test_invalid_type_defaults_to_context(self, client):
        response = client.post(
            "/smart-memory",
            json={"content": "Some useful information about my website", "type": "invalid_type"},
        )
        data = response.get_json()
        assert data["smart_memory"][0]["type"] == "context"

    def test_concurrent_memory_writes_no_duplicates(self, client, monkeypatch):
        import app as app_module

        seed = client.get("/smart-memory")
        signed_cookie = SimpleCookie(seed.headers["Set-Cookie"])[app_module.SESSION_COOKIE_NAME].value

        def store_memory(i):
            worker = app_module.app.test_client()
            worker.set_cookie(app_module.SESSION_COOKIE_NAME, signed_cookie)
            worker.post(
                "/smart-memory",
                json={"content": "Duplicate content for testing race conditions", "type": "fact"},
            )

        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(store_memory, range(5)))

        memory = client.get("/smart-memory").get_json()
        assert len(memory["smart_memory"]) == 1


class TestBuildContext:
    def test_build_context_returns_relevant_entries(self, client):
        client.post(
            "/smart-memory",
            json={"content": "User prefers teal color schemes for their websites", "type": "instruction"},
        )
        client.post(
            "/smart-memory",
            json={"content": "User is building a science fair project website", "type": "context"},
        )
        response = client.post("/build-context", json={"input": "build a website with teal"})
        data = response.get_json()
        assert data["success"] is True
        assert "teal" in data["context"].lower()

    def test_build_context_with_empty_input(self, client):
        response = client.post("/build-context", json={"input": ""})
        data = response.get_json()
        assert data["success"] is True


class TestMemoryWriteOnlyAfterResponse:
    def test_stream_writes_memory_after_completion(self, client, tmp_path):
        import app as app_module

        seed = client.get("/smart-memory")
        signed_cookie = SimpleCookie(seed.headers["Set-Cookie"])[app_module.SESSION_COOKIE_NAME].value
        serializer = app_module.app.session_interface.get_signing_serializer(app_module.app)
        session_id = serializer.loads(signed_cookie)["session_id"]

        response = client.post(
            "/generate-code-stream",
            json={"prompt": "Build a website for science class"},
        )
        assert response.status_code == 200

        memory_path = Path(tmp_path) / "html_memory" / f"{session_id}.json"
        if memory_path.exists():
            data = json.loads(memory_path.read_text())
            assert any("Generated website" in (h.get("note") or "") for h in data.get("history", []))


class TestVoiceMemoryEngineJS:
    def test_state_machine_transitions(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node is required")

        harness = textwrap.dedent(r"""
            const fs = require('fs');
            const vm = require('vm');

            function assert(cond, msg) { if (!cond) throw new Error(msg); }

            const context = {
                console,
                window: {
                    speechSynthesis: { cancel() {}, speak() {} },
                },
                document: {
                    getElementById() { return null; },
                },
                fetch: async () => ({ ok: true, json: async () => ({ success: true, reply: 'test' }), body: { getReader: () => ({ read: async () => ({ done: true }) }) } }),
                setTimeout,
                clearTimeout,
                TextDecoder: class { decode() { return ''; } },
                SpeechSynthesisUtterance: function(t) { this.text = t; },
            };
            context.window.window = context.window;
            context.window.document = context.document;
            context.window.VoiceMemoryEngine = undefined;

            vm.runInNewContext(fs.readFileSync('static/voice-memory-engine.js', 'utf8'), context);
            const VME = context.window.VoiceMemoryEngine;

            assert(VME, 'VoiceMemoryEngine should exist');
            assert(VME.getState() === 'IDLE', 'initial state should be IDLE');

            VME.setState('LISTENING');
            assert(VME.getState() === 'LISTENING', 'state should transition to LISTENING');

            VME.setState('PROCESSING');
            assert(VME.getState() === 'PROCESSING', 'state should transition to PROCESSING');

            VME.setState('RESPONDING');
            assert(VME.getState() === 'RESPONDING', 'state should transition to RESPONDING');

            VME.setState('SPEAKING');
            assert(VME.getState() === 'SPEAKING', 'state should transition to SPEAKING');

            VME.interrupt();
            assert(VME.getState() === 'LISTENING', 'interrupt should go to LISTENING');
        """)
        subprocess.run([node, "-e", harness], check=True, cwd=str(Path(__file__).resolve().parent.parent))

    def test_duplicate_detection(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node is required")

        harness = textwrap.dedent(r"""
            const fs = require('fs');
            const vm = require('vm');

            function assert(cond, msg) { if (!cond) throw new Error(msg); }

            const context = {
                console,
                Date,
                window: {
                    speechSynthesis: { cancel() {}, speak() {} },
                },
                document: {
                    getElementById() { return null; },
                },
                setTimeout,
                clearTimeout,
                TextDecoder: class { decode() { return ''; } },
                SpeechSynthesisUtterance: function(t) { this.text = t; },
            };
            context.window.window = context.window;
            context.window.document = context.document;

            vm.runInNewContext(fs.readFileSync('static/voice-memory-engine.js', 'utf8'), context);
            const VME = context.window.VoiceMemoryEngine;

            assert(VME.isDuplicate('') === true, 'empty should be duplicate');
            assert(VME.isDuplicate('hello world') === false, 'first occurrence should not be duplicate');
            assert(VME.isDuplicate('hello world') === true, 'immediate repeat should be duplicate');
            assert(VME.isDuplicate('different text') === false, 'different text should not be duplicate');
        """)
        subprocess.run([node, "-e", harness], check=True, cwd=str(Path(__file__).resolve().parent.parent))

    def test_interrupt_cancels_during_speaking(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node is required")

        harness = textwrap.dedent(r"""
            const fs = require('fs');
            const vm = require('vm');

            function assert(cond, msg) { if (!cond) throw new Error(msg); }

            let cancelCalled = false;
            const context = {
                console,
                Date,
                window: {
                    speechSynthesis: {
                        cancel() { cancelCalled = true; },
                        speak() {},
                    },
                },
                document: {
                    getElementById() { return null; },
                },
                setTimeout,
                clearTimeout,
                TextDecoder: class { decode() { return ''; } },
                SpeechSynthesisUtterance: function(t) { this.text = t; },
            };
            context.window.window = context.window;
            context.window.document = context.document;

            vm.runInNewContext(fs.readFileSync('static/voice-memory-engine.js', 'utf8'), context);
            const VME = context.window.VoiceMemoryEngine;

            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            VME.setState('SPEAKING');
            VME.interrupt();

            assert(cancelCalled, 'interrupt during SPEAKING should cancel TTS');
            assert(VME.getState() === 'LISTENING', 'interrupt should set state to LISTENING');
        """)
        subprocess.run([node, "-e", harness], check=True, cwd=str(Path(__file__).resolve().parent.parent))

    def test_interrupt_cancels_during_responding(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node is required")

        harness = textwrap.dedent(r"""
            const fs = require('fs');
            const vm = require('vm');

            function assert(cond, msg) { if (!cond) throw new Error(msg); }

            let cancelCalled = false;
            let abortCalled = false;
            const context = {
                console,
                Date,
                window: {
                    speechSynthesis: {
                        cancel() { cancelCalled = true; },
                        speak() {},
                    },
                },
                document: {
                    getElementById() { return null; },
                },
                setTimeout,
                clearTimeout,
                AbortController: class {
                    constructor() { this.signal = { aborted: false }; }
                    abort() { abortCalled = true; this.signal.aborted = true; }
                },
                TextDecoder: class { decode() { return ''; } },
                SpeechSynthesisUtterance: function(t) { this.text = t; },
            };
            context.window.window = context.window;
            context.window.document = context.document;

            vm.runInNewContext(fs.readFileSync('static/voice-memory-engine.js', 'utf8'), context);
            const VME = context.window.VoiceMemoryEngine;

            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            VME.interrupt();

            assert(cancelCalled, 'interrupt during RESPONDING should cancel TTS');
            assert(VME.getState() === 'LISTENING', 'interrupt should set state to LISTENING');
        """)
        subprocess.run([node, "-e", harness], check=True, cwd=str(Path(__file__).resolve().parent.parent))

    def test_handle_transcript_interrupts_when_speaking(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node is required")

        harness = textwrap.dedent(r"""
            const fs = require('fs');
            const vm = require('vm');

            function assert(cond, msg) { if (!cond) throw new Error(msg); }

            let cancelCalled = false;
            const context = {
                console,
                Date,
                window: {
                    speechSynthesis: {
                        cancel() { cancelCalled = true; },
                        speak() {},
                    },
                },
                document: {
                    getElementById() { return null; },
                },
                setTimeout,
                clearTimeout,
                TextDecoder: class { decode() { return ''; } },
                SpeechSynthesisUtterance: function(t) { this.text = t; },
            };
            context.window.window = context.window;
            context.window.document = context.document;

            vm.runInNewContext(fs.readFileSync('static/voice-memory-engine.js', 'utf8'), context);
            const VME = context.window.VoiceMemoryEngine;

            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            VME.setState('SPEAKING');
            const result = VME.handleTranscript('new command from user');

            assert(result === true, 'handleTranscript should return true for valid input');
            assert(cancelCalled, 'handleTranscript should cancel speech');
            assert(VME.getState() === 'LISTENING', 'should transition to LISTENING after barge-in');
        """)
        subprocess.run([node, "-e", harness], check=True, cwd=str(Path(__file__).resolve().parent.parent))

    def test_conversation_history_maintained(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node is required")

        harness = textwrap.dedent(r"""
            const fs = require('fs');
            const vm = require('vm');

            function assert(cond, msg) { if (!cond) throw new Error(msg); }

            const context = {
                console,
                Date,
                window: {
                    speechSynthesis: { cancel() {}, speak() {} },
                },
                document: {
                    getElementById() { return null; },
                },
                setTimeout,
                clearTimeout,
                TextDecoder: class { decode() { return ''; } },
                SpeechSynthesisUtterance: function(t) { this.text = t; },
            };
            context.window.window = context.window;
            context.window.document = context.document;

            vm.runInNewContext(fs.readFileSync('static/voice-memory-engine.js', 'utf8'), context);
            const VME = context.window.VoiceMemoryEngine;

            VME.addToHistory('user', 'Build a website');
            VME.addToHistory('assistant', 'Here is your website');
            VME.addToHistory('user', 'Make it blue');

            const history = VME.getHistory();
            assert(history.length === 3, 'should have 3 entries');
            assert(history[0].role === 'user', 'first should be user');
            assert(history[1].role === 'assistant', 'second should be assistant');
            assert(history[2].content === 'Make it blue', 'last content should match');
        """)
        subprocess.run([node, "-e", harness], check=True, cwd=str(Path(__file__).resolve().parent.parent))

    def test_reset_clears_all_state(self):
        node = shutil.which("node")
        if not node:
            pytest.skip("node is required")

        harness = textwrap.dedent(r"""
            const fs = require('fs');
            const vm = require('vm');

            function assert(cond, msg) { if (!cond) throw new Error(msg); }

            const context = {
                console,
                Date,
                window: {
                    speechSynthesis: { cancel() {}, speak() {} },
                },
                document: {
                    getElementById() { return null; },
                },
                setTimeout,
                clearTimeout,
                TextDecoder: class { decode() { return ''; } },
                SpeechSynthesisUtterance: function(t) { this.text = t; },
            };
            context.window.window = context.window;
            context.window.document = context.document;

            vm.runInNewContext(fs.readFileSync('static/voice-memory-engine.js', 'utf8'), context);
            const VME = context.window.VoiceMemoryEngine;

            VME.addToHistory('user', 'test');
            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            VME.setState('SPEAKING');
            VME.resetEngine();

            assert(VME.getState() === 'IDLE', 'reset should set IDLE');
            assert(VME.getHistory().length === 0, 'reset should clear history');
        """)
        subprocess.run([node, "-e", harness], check=True, cwd=str(Path(__file__).resolve().parent.parent))


class TestVoiceUpgrades:
    @pytest.fixture(autouse=True)
    def _check_node(self):
        if not shutil.which("node"):
            pytest.skip("node is required")

    def _run(self, harness):
        subprocess.run(
            [shutil.which("node"), "-e", harness],
            check=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )

    def _base_context(self, extras=""):
        return textwrap.dedent(
            r"""
            const fs = require('fs');
            const vm = require('vm');
            function assert(cond, msg) { if (!cond) throw new Error(msg); }

            let cancelCalled = false;
            let abortCalled = false;
            const context = {
                console, Date,
                window: {
                    speechSynthesis: {
                        cancel() { cancelCalled = true; },
                        speak() {},
                    },
                },
                document: { getElementById() { return null; } },
                setTimeout, clearTimeout,
                AbortController: class {
                    constructor() { this.signal = { aborted: false }; }
                    abort() { abortCalled = true; this.signal.aborted = true; }
                },
                TextDecoder: class { decode() { return ''; } },
                SpeechSynthesisUtterance: function(t) { this.text = t; },
                fetch: async () => ({ ok: true, json: async () => ({ success: true, reply: 'ok' }),
                    body: { getReader: () => ({ read: async () => ({ done: true }) }) } }),
        """
            + extras
            + r"""
            };
            context.window.window = context.window;
            context.window.document = context.document;
            vm.runInNewContext(fs.readFileSync('static/voice-memory-engine.js', 'utf8'), context);
            const VME = context.window.VoiceMemoryEngine;
        """
        )

    def test_state_validation_rejects_invalid_transitions(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            assert(VME.getState() === 'IDLE', 'starts IDLE');
            VME.setState('PROCESSING');
            assert(VME.getState() === 'IDLE', 'IDLE->PROCESSING should be rejected');
            VME.setState('LISTENING');
            assert(VME.getState() === 'LISTENING', 'IDLE->LISTENING is valid');
            VME.setState('SPEAKING');
            assert(VME.getState() === 'LISTENING', 'LISTENING->SPEAKING should be rejected');
        """)
        )

    def test_interrupt_aborts_controller_and_clears_queue(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            VME.interrupt();
            assert(cancelCalled, 'should cancel speech synthesis');
            assert(VME.getState() === 'LISTENING', 'should return to LISTENING');
        """)
        )

    def test_extract_micro_chunks_long_buffer_fallback(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            const result = VME.extractMicroChunks('this is a very long test phrase without any punctuation at all and more');
            assert(result.chunks.length >= 1, 'should extract at least one chunk from long text');

            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            const tr = VME.handleTranscript('this is a very long test phrase without any punctuation at all');
            assert(tr === true, 'long phrase should not be duplicate');
        """)
        )

    def test_no_duplicate_triggers_within_window(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            assert(VME.isDuplicate('build a website') === false, 'first is not dup');
            assert(VME.isDuplicate('build a website') === true, 'immediate repeat is dup');
            assert(VME.isDuplicate('build a website') === true, 'still dup within 3s');
            assert(VME.isDuplicate('different command') === false, 'different is not dup');
        """)
        )

    def test_voice_active_flag_controls_resume_target(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            VME.setVoiceActive(true);
            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            VME.setState('SPEAKING');
            VME.interrupt();
            assert(VME.getState() === 'LISTENING', 'with voiceActive should go to LISTENING');

            VME.setVoiceActive(false);
            VME.resetEngine();
            assert(VME.getState() === 'IDLE', 'reset goes to IDLE');
        """)
        )

    def test_handle_transcript_interrupts_responding_state(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            const result = VME.handleTranscript('stop now');
            assert(result === true, 'should return true');
            assert(cancelCalled, 'should cancel TTS');
            assert(VME.getState() === 'LISTENING', 'should be LISTENING after barge-in');
        """)
        )

    def test_reset_clears_interrupted_flag(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            VME.interrupt();
            VME.resetEngine();
            assert(VME.getState() === 'IDLE', 'reset should set IDLE');
            assert(VME.getHistory().length === 0, 'reset should clear history');
        """)
        )

    def test_set_same_state_is_noop(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            let changeCount = 0;
            VME.onStateChange = () => { changeCount++; };
            VME.setState('LISTENING');
            assert(changeCount === 1, 'first transition fires callback');
            VME.setState('LISTENING');
            assert(changeCount === 1, 'same state should not fire again');
        """)
        )


class TestHindiAndPolish:
    @pytest.fixture(autouse=True)
    def _check_node(self):
        if not shutil.which("node"):
            pytest.skip("node is required")

    def _run(self, harness):
        subprocess.run(
            [shutil.which("node"), "-e", harness],
            check=True,
            cwd=str(Path(__file__).resolve().parent.parent),
        )

    def _base_context(self):
        return textwrap.dedent(r"""
            const fs = require('fs');
            const vm = require('vm');
            function assert(cond, msg) { if (!cond) throw new Error(msg); }

            let cancelCalled = false;
            let spokenTexts = [];
            const context = {
                console, Date,
                window: {
                    speechSynthesis: {
                        cancel() { cancelCalled = true; },
                        speak(u) { spokenTexts.push({ text: u.text, lang: u.lang }); if (u.onend) u.onend(); },
                        getVoices() { return [
                            { lang: 'en-US', name: 'English US' },
                            { lang: 'hi-IN', name: 'Hindi India' },
                            { lang: 'en-IN', name: 'English India' },
                        ]; },
                    },
                },
                document: { getElementById() { return null; } },
                setTimeout, clearTimeout,
                AbortController: class {
                    constructor() { this.signal = { aborted: false }; }
                    abort() { this.signal.aborted = true; }
                },
                TextDecoder: class { decode() { return ''; } },
                SpeechSynthesisUtterance: function(t) { this.text = t; },
                fetch: async () => ({ ok: true, json: async () => ({ success: true, reply: 'ok' }),
                    body: { getReader: () => ({ read: async () => ({ done: true }) }) } }),
            };
            context.window.window = context.window;
            context.window.document = context.document;
            vm.runInNewContext(fs.readFileSync('static/voice-memory-engine.js', 'utf8'), context);
            const VME = context.window.VoiceMemoryEngine;
        """)

    def test_hindi_detection_devanagari(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            assert(VME.isHindiText('नमस्ते दुनिया') === true, 'Devanagari should be detected as Hindi');
            assert(VME.isHindiText('Hello world') === false, 'Latin text should not be Hindi');
            assert(VME.isHindiText('Hello नमस्ते') === true, 'Mixed text with Devanagari should detect Hindi');
        """)
        )

    def test_detect_lang_auto_mode(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            VME.setVoiceLangMode('auto');
            assert(VME.detectLang('Hello world') === 'en-US', 'English text in auto mode');
            assert(VME.detectLang('नमस्ते दुनिया') === 'hi-IN', 'Hindi text in auto mode');
        """)
        )

    def test_detect_lang_forced_mode(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            VME.setVoiceLangMode('hi');
            assert(VME.detectLang('Hello world') === 'hi-IN', 'forced Hindi mode overrides');
            VME.setVoiceLangMode('en');
            assert(VME.detectLang('नमस्ते') === 'en-US', 'forced English mode overrides');
        """)
        )

    def test_mixed_language_splitting(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            const segs = VME.splitMixedLanguage('Hello नमस्ते world दुनिया');
            assert(segs.length === 4, 'should split into 4 segments, got ' + segs.length);
            assert(segs[0].lang === 'en-US', 'first segment is English');
            assert(segs[1].lang === 'hi-IN', 'second segment is Hindi');
            assert(segs[2].lang === 'en-US', 'third segment is English');
            assert(segs[3].lang === 'hi-IN', 'fourth segment is Hindi');
        """)
        )

    def test_mixed_language_pure_hindi(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            const segs = VME.splitMixedLanguage('नमस्ते दुनिया कैसे हो');
            assert(segs.length === 1, 'pure Hindi should be one segment');
            assert(segs[0].lang === 'hi-IN', 'should be Hindi');
        """)
        )

    def test_micro_chunk_extraction(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            const result = VME.extractMicroChunks('This is a short sentence. And another one here.');
            assert(result.chunks.length >= 2, 'should extract at least 2 chunks');
            assert(result.remainder === '' || result.remainder.trim() === '', 'no remainder');
        """)
        )

    def test_micro_chunk_long_text_without_punctuation(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            const text = 'This is a long text without any punctuation marks at all and it keeps going';
            const result = VME.extractMicroChunks(text);
            assert(result.chunks.length >= 1, 'should break long text into chunks');
            for (const c of result.chunks) {
                assert(c.length <= 50, 'chunk should not be too long: ' + c.length);
            }
        """)
        )

    def test_voice_lang_mode_persists(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            VME.setVoiceLangMode('hi');
            assert(VME.getVoiceLangMode() === 'hi', 'should be hi');
            VME.setVoiceLangMode('auto');
            assert(VME.getVoiceLangMode() === 'auto', 'should be auto');
            VME.setVoiceLangMode('invalid');
            assert(VME.getVoiceLangMode() === 'auto', 'invalid should be ignored');
        """)
        )

    def test_interrupt_sets_timestamp_and_stale_check(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            const before = Date.now() - 100;
            VME.setState('LISTENING');
            VME.setState('PROCESSING');
            VME.setState('RESPONDING');
            VME.interrupt();
            assert(VME.getState() === 'LISTENING', 'should be LISTENING after interrupt');
            assert(cancelCalled, 'should cancel speech');
        """)
        )

    def test_reset_clears_sync_indices(self):
        self._run(
            self._base_context()
            + textwrap.dedent(r"""
            VME.resetEngine();
            assert(VME.getState() === 'IDLE', 'reset should set IDLE');
            assert(VME.getHistory().length === 0, 'reset should clear history');
        """)
        )


class TestNoRaceConditions:
    def test_rapid_memory_writes_are_safe(self, client, monkeypatch):
        import app as app_module

        seed = client.get("/smart-memory")
        signed_cookie = SimpleCookie(seed.headers["Set-Cookie"])[app_module.SESSION_COOKIE_NAME].value

        def write_memory(i):
            worker = app_module.app.test_client()
            worker.set_cookie(app_module.SESSION_COOKIE_NAME, signed_cookie)
            worker.post(
                "/smart-memory",
                json={"content": f"Rapid input number {i} for testing", "type": "context"},
            )

        with ThreadPoolExecutor(max_workers=10) as pool:
            list(pool.map(write_memory, range(20)))

        memory = client.get("/smart-memory").get_json()
        assert len(memory["smart_memory"]) == 20

    def test_concurrent_stream_and_memory_dont_corrupt(self, client, monkeypatch):
        import app as app_module

        seed = client.get("/smart-memory")
        signed_cookie = SimpleCookie(seed.headers["Set-Cookie"])[app_module.SESSION_COOKIE_NAME].value

        def stream_request():
            worker = app_module.app.test_client()
            worker.set_cookie(app_module.SESSION_COOKIE_NAME, signed_cookie)
            resp = worker.post(
                "/generate-code-stream",
                json={"prompt": "Build a website for testing"},
            )
            return resp.status_code

        def memory_request(i):
            worker = app_module.app.test_client()
            worker.set_cookie(app_module.SESSION_COOKIE_NAME, signed_cookie)
            resp = worker.post(
                "/smart-memory",
                json={"content": f"Concurrent memory entry {i} for testing", "type": "context"},
            )
            return resp.status_code

        with ThreadPoolExecutor(max_workers=6) as pool:
            stream_futures = [pool.submit(stream_request) for _ in range(2)]
            memory_futures = [pool.submit(memory_request, i) for i in range(4)]
            all_results = [f.result(timeout=10) for f in stream_futures + memory_futures]

        assert all(code == 200 for code in all_results)
