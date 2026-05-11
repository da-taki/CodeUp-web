'use strict';

let editor;
window._editorReady = false;
window._editorReadyQueue = [];
let audioCtx = null;
let snippetsCache = [];
let pendingConfirm = null;
let lastSpokenText = null;

// Per-tab unique ID so quiz/bug-challenge state cannot bleed across tabs.
// All transient interactive state is scoped under window._tabState[_tabId].
const _tabId = (typeof crypto !== 'undefined' && crypto.randomUUID)
  ? crypto.randomUUID()
  : 'tab-' + Math.random().toString(36).slice(2);
window._tabState = window._tabState || {};
window._tabState[_tabId] = window._tabState[_tabId] || {};
function tabState() { return window._tabState[_tabId]; }
let isListening = false;
let recognition = null;
let _restartTimer = null;
// Voice paused state — recognition is still running but commands are dropped
// until the user says "resume". We do NOT persist this across reloads —
// a fresh page should always start unpaused.
let _voicePaused = false;
try { localStorage.removeItem('codeup_voice_paused'); } catch (e) {}

// Watchdog: track last time recognition was confirmed active. If voice is
// supposedly listening but we haven't seen activity in a while, the session
// may have silently died (common during long pauses). The watchdog kicks it
// back to life.
let _lastRecognitionActivity = Date.now();
let _watchdogTimer = null;

function _startRecognitionWatchdog() {
  if (_watchdogTimer) return;
  _watchdogTimer = setInterval(() => {
    if (!isListening) return;  // not running, nothing to watch
    const idle = Date.now() - _lastRecognitionActivity;
    // 45s of silence = Chrome has likely auto-stopped. Force a kick.
    if (idle > 45000) {
      _debugLog('Watchdog: recognition idle for', idle, 'ms — kicking');
      _lastRecognitionActivity = Date.now();  // reset to avoid kick loops
      try {
        // Stop and restart to force a clean session. onend will trigger
        // the auto-restart chain.
        recognition.stop();
      } catch (e) {
        // If stop fails, try start directly
        try { recognition.start(); } catch (e2) {
          _debugLog('Watchdog kick failed:', e2.message);
        }
      }
    }
  }, 15000);  // check every 15s
}

function _stopRecognitionWatchdog() {
  if (_watchdogTimer) {
    clearInterval(_watchdogTimer);
    _watchdogTimer = null;
  }
}
let _voiceStartIsUserInitiated = false;
let _loadingSnippets = false;
// Stored on window so the language-change handler in index.html can reset it.
window._apiKeyPromptShown = false;

// Pre-flight inputs queue (Mechanism A). Mirrors the inputs the user has
// declared via voice or the inputs panel. Sent with every /run call.
let _preflightInputs = [];
// Exposed for inline scripts in index.html that can't see module-scoped `let`.
window.getPreflightInputs = () => _preflightInputs.slice();
// Live input mode toggle (Mechanism B). When true, "run" goes to /run-stream
// instead of /run.
let _liveInputMode = false;

// Active streaming run state (only one at a time per tab)
let _activeStreamRun = null;  // {runId, eventSource, awaitingPrompt, awaitingResolve}

// Audio heartbeat timer — soft tone every 500ms while a run is in flight
let _heartbeatTimer = null;

// Last output stored for diff narration and bookmarks
let _lastOutput = '';
let _lastOutputDiff = null;

// Autosave config
const AUTOSAVE_INTERVAL_MS = 30000;
let _autosaveTimer = null;
let _autosaveLastCode = '';
const AUTOSAVE_KEY = 'codeup_autosave_draft';

// Set window.CODEUP_DEBUG = true in the browser console to see debug logs.
// Off by default so deployments don't spam the console.
const _debugLog = (...args) => {
  if (typeof window !== 'undefined' && window.CODEUP_DEBUG) {
    console.log(...args);
  }
};

// Utility: calculate indentation level (spaces and tabs)
function getIndentLevel(line) {
  let indent = 0;
  for (let i = 0; i < line.length; i++) {
    if (line[i] === ' ')      indent += 0.25;
    else if (line[i] === '\t') indent += 1;
    else break;
  }
  return indent;
}

// Escape regex special characters in user-supplied strings
function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// ---------- APP STATE ----------
const AppState = {
  isListening:  false,
  isSpeaking:   false,
  isExecuting:  false,
};

// Single helper to toggle visibility using the `hidden` attribute consistently.
// Using style.display would permanently override the `hidden` attribute from HTML.
function showEl(el) {
  if (!el) return;
  el.removeAttribute('hidden');
}
function hideEl(el) {
  if (!el) return;
  el.setAttribute('hidden', '');
}

// ---------- SPEECH MANAGER ----------
const SpeechManager = (function () {
  try {
    const queue = [];
    let currentUtterance = null;
    let _lastSynthKick = 0;

    function dequeue() {
      // Gate on the actual synthesis state, not just our local pointer.
      // Chrome can have currentUtterance==null while speechSynthesis is
      // still draining a previously-cancelled utterance; if we dequeue
      // into that gap we get doubled speech.
      if (currentUtterance || !queue.length) return;
      if (window.speechSynthesis && window.speechSynthesis.speaking) {
        // Try again once the engine actually drains
        setTimeout(dequeue, 80);
        return;
      }
      speakNow(queue.shift());
    }

    function speakNow(item) {
      if (!('speechSynthesis' in window) || !item || !item.text) {
        if (item && item.resolve) item.resolve();
        return;
      }
      AppState.isSpeaking = true;
      currentUtterance = new SpeechSynthesisUtterance(item.text);

      const now = Date.now();
      if (now - _lastSynthKick > 8000) {
        try {
          window.speechSynthesis.pause();
          window.speechSynthesis.resume();
        } catch (e) {}

        _lastSynthKick = now;
      }

      currentUtterance.rate  = item.rate  || 1;
      currentUtterance.pitch = item.pitch || 1;
      currentUtterance.lang  = (typeof getLanguage === 'function' && getLanguage() === 'hi') ? 'hi-IN' : 'en-US';

      let finished = false;
      let started = false;
      const cleanup = () => {
        if (finished) return;
        finished = true;
        AppState.isSpeaking = false;
        currentUtterance = null;
        if (item.timeoutId) clearTimeout(item.timeoutId);
        if (item.resolve) item.resolve();
        dequeue();
      };

      currentUtterance.onstart = () => {
        started = true;
      };

      currentUtterance.onend = cleanup;
      currentUtterance.onerror = cleanup;

      item.timeoutId = setTimeout(cleanup, 30000);

      setTimeout(() => {
        if (!started && !finished) {
          try {
            window.speechSynthesis.cancel();
          } catch (e) {}

          cleanup();
        }
      }, 1200);

      window.speechSynthesis.speak(currentUtterance);
    }

    function enqueue(text, opts = {}) {
      return new Promise(resolve => {
        queue.push({ text, ...opts, resolve });
        dequeue();
      });
    }

    function cancelAll() {
      queue.length = 0;
      try { window.speechSynthesis.cancel(); } catch (e) {}
      // Chrome leaves speechSynthesis.speaking === true after cancel() in many
      // cases. Hit it with multiple cancels staggered across a wider window
      // so subsequent enqueue() calls don't see a stale "speaking" state.
      [50, 150, 300, 500].forEach(delay => {
        setTimeout(() => {
          try {
            if (window.speechSynthesis && window.speechSynthesis.speaking) {
              window.speechSynthesis.cancel();
            }
          } catch (e) {}
        }, delay);
      });
      AppState.isSpeaking = false;
      currentUtterance = null;
    }

    return { enqueue, cancelAll };
  } catch (e) {
    return { enqueue: () => Promise.resolve(), cancelAll: () => {} };
  }
})();

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// ---------- SONIFICATION MANAGER ----------
const SonificationManager = (function () {
  const jobs = new Map();

  function ensureAudio() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') {
      audioCtx.resume().catch(e => console.warn('AudioContext resume failed:', e));
    }
    return audioCtx;
  }

  function playTone(freq, duration = 0.08, vol = 0.1) {
    const reduced = (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) ||
                    document.body.classList.contains('theme-reduced-motion');
    if (reduced) return;
    try {
      const ctx = ensureAudio();
      const osc  = ctx.createOscillator();
      const gain = ctx.createGain();
      gain.gain.value   = vol;
      osc.frequency.value = freq;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + duration);
      setTimeout(() => {
        try { osc.disconnect(); gain.disconnect(); } catch (e) {}
      }, (duration + 0.1) * 1000);
    } catch (e) {}
  }

  return {
    startJob(id)         { jobs.set(id, []); },
    pushTimer(id, t)     { const a = jobs.get(id); if (a) a.push(t); },
    cancelJob(id)        { (jobs.get(id) || []).forEach(t => clearTimeout(t)); jobs.delete(id); },
    clearAll()           { for (const [, a] of jobs) a.forEach(t => clearTimeout(t)); jobs.clear(); },
    playTone,
  };
})();

// ---------- ERROR BEACON MANAGER ----------
const ErrorBeaconManager = (function () {
  let intervalId = null;
  let currentLine = null;
  let currentSeverity = null;

  function start(line, severity = 'high') {
    stop();
    currentLine = line; currentSeverity = severity;
    const freq     = severity === 'high' ? 800 : severity === 'medium' ? 600 : 400;
    const interval = severity === 'high' ? 2000 : severity === 'medium' ? 3000 : 4000;
    intervalId = setInterval(() => SonificationManager.playTone(freq, 0.12, 0.05), interval);
  }

  function stop() {
    if (intervalId) { clearInterval(intervalId); intervalId = null; }
    currentLine = null; currentSeverity = null;
  }

  return {
    start, stop,
    downgrade(s) { if (currentLine) start(currentLine, s); },
    getState: () => ({ active: !!intervalId, line: currentLine, severity: currentSeverity }),
  };
})();

// ---------- AUDIO CUES ----------
function cueSuccess() { SonificationManager.playTone(900, 0.05, 0.08); }
function cueError()   { SonificationManager.playTone(200, 0.15, 0.08); }

const TONES = {
  indent0: 200, indent1: 300, indent2: 450, indent3: 600, indent4: 800,
  function: 900, class: 1000, loop: 400, conditional: 500, comment: 150, blank: 100,
};

function sonifyLine(lineContent, indentLevel) {
  const trimmed = lineContent.trim();
  SonificationManager.playTone(TONES[`indent${Math.min(indentLevel, 4)}`], 0.05, 0.08);
  setTimeout(() => {
    if (!trimmed)                                              SonificationManager.playTone(TONES.blank,        0.03, 0.05);
    else if (trimmed.startsWith('#'))                          SonificationManager.playTone(TONES.comment,      0.06, 0.06);
    else if (trimmed.startsWith('def '))                       SonificationManager.playTone(TONES.function,     0.08, 0.1);
    else if (trimmed.startsWith('class '))                     SonificationManager.playTone(TONES.class,        0.08, 0.12);
    else if (trimmed.startsWith('for ') || trimmed.startsWith('while ')) SonificationManager.playTone(TONES.loop, 0.08, 0.09);
    else if (trimmed.startsWith('if ') || trimmed.startsWith('elif ') || trimmed.startsWith('else')) SonificationManager.playTone(TONES.conditional, 0.08, 0.09);
  }, 60);
}

// ---------- LINE READING ----------
async function readLineEnhanced(line) {
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const maxLine = model.getLineCount();
  if (line < 1 || line > maxLine) {
    const msg = `Line ${line} is out of range. File has ${maxLine} lines.`;
    out(msg); speak(msg); return;
  }
  const lineText = model.getLineContent(line);
  const indent = Math.floor(getIndentLevel(lineText));
  // Sonify first, then speak
  sonifyLine(lineText, indent);
  setTimeout(() => {
    const msg = `Line ${line}: ${lineText || 'empty line'}`;
    out(msg);
    speak(msg);
  }, 200);
}

// ---------- BLOCK SONIFICATION ----------
async function sonifyCurrentBlock() {
  const model = getModel();
  if (!model) return;
  const pos         = editor.getPosition() || { lineNumber: 1 };
  const currentLine = pos.lineNumber;
  const lines       = getCode().split('\n');
  const currentIndent = getIndentLevel(lines[currentLine - 1]);

  let startLine = currentLine;
  let endLine   = currentLine;

  for (let i = currentLine - 2; i >= 0; i--) {
    if (getIndentLevel(lines[i]) < currentIndent && lines[i].trim()) { startLine = i + 1; break; }
  }
  for (let i = currentLine; i < lines.length; i++) {
    if (getIndentLevel(lines[i]) < currentIndent && lines[i].trim()) { endLine = i + 1; break; }
    if (i === lines.length - 1) endLine = i + 1;
  }

  SonificationManager.clearAll();
  speak(`Sonifying block from line ${startLine} to line ${endLine}`);

  const jobId = Date.now();
  SonificationManager.startJob(jobId);
  let delay = 0;
  for (let i = startLine - 1; i < endLine; i++) {
    const line   = lines[i];
    const indent = Math.floor(getIndentLevel(line));
    const t = setTimeout(() => { try { sonifyLine(line, indent); } catch (e) {} }, delay);
    SonificationManager.pushTimer(jobId, t);
    delay += 120;
  }
  const fin = setTimeout(() => { speak('Block sonification complete.'); SonificationManager.cancelJob(jobId); }, delay + 200);
  SonificationManager.pushTimer(jobId, fin);
}

// ---------- NAVIGATION HISTORY ----------
let navigationHistory = [];
let historyIndex = -1;
const MAX_HISTORY = 50;

function recordNavigation(line) {
  if (navigationHistory.length > 0 && navigationHistory[navigationHistory.length - 1] === line) return;
  navigationHistory.push(line);
  if (navigationHistory.length > MAX_HISTORY) navigationHistory.shift();
  historyIndex = navigationHistory.length - 1;
}

function navigateBack() {
  if (!ensureNotExecuting(() => navigateBack(), 'navigate back')) return;
  if (historyIndex <= 0) { speak('Already at the oldest position in history.'); return; }
  SpeechManager.cancelAll();
  historyIndex--;
  const line = navigationHistory[historyIndex];
  gotoLine(line, false);
  speak(`Navigated back to line ${line}.`);
}

function navigateForward() {
  if (!ensureNotExecuting(() => navigateForward(), 'navigate forward')) return;
  if (historyIndex >= navigationHistory.length - 1) { speak('Already at the newest position in history.'); return; }
  SpeechManager.cancelAll();
  historyIndex++;
  const line = navigationHistory[historyIndex];
  gotoLine(line, false);
  speak(`Navigated forward to line ${line}.`);
}

function showNavigationHistory() {
  if (navigationHistory.length === 0) { speak('Navigation history is empty.'); out('Navigation history is empty.'); return; }
  const history = navigationHistory.slice(-10).map((line, i) => `${i + 1}. Line ${line}`).join('\n');
  out(`Recent navigation history:\n${history}`);
  speak(`You have ${navigationHistory.length} positions in history. Showing last 10.`);
  speak(history);
}

// ---------- VARIABLE TRACKING ----------
async function listVariables() {
  if (!ensureNotExecuting(() => listVariables(), 'list variables')) return;
  const model = getModel();
  if (!model) return;
  const pos = editor.getPosition() || { lineNumber: 1 };
  showAI('Analyzing variables...');
  speak('Analyzing variables in scope.');
  try {
    const res  = await fetch('/track-variables', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: getCode(), line: pos.lineNumber }),
    });
    const data = await res.json();
    if (data.success) {
      if (data.variables.length === 0) {
        out(`No variables found in ${data.current_scope}.`);
        speak(`No variables found in ${data.current_scope}.`);
      } else {
        const varList = data.variables.map(v =>
          `${v.name} (${v.phonetic}): used ${v.usage_count} times, defined at line ${v.first_line}`
        ).join('\n');
        out(`Variables in ${data.current_scope}:\n\n${varList}`);

        // Do not clear the speech queue here.
        // Variable narration should flow naturally in sequence.
        // cancelAll() was interrupting active utterances and
        // occasionally causing Chrome speech synthesis deadlocks.
        speak(`Found ${data.variables.length} variables in ${data.current_scope}.`);

        data.variables.slice(0, 5).forEach(v =>
          speak(`${v.phonetic}, used ${v.usage_count} times.`)
        );

        if (data.variables.length > 5) {
          speak(`And ${data.variables.length - 5} more. Check output for full list.`);
        }
      }
    } else {
      const msg = data.message || 'Failed to analyze variables.';
      out(msg); speak(msg);
    }
  } catch (e) {
    console.error(e); out('Variable tracking failed.'); speak('Variable tracking failed.');
  } finally {
    hideAI();
  }
}

async function findVariable(varName) {
  if (!varName) { speak('Please specify a variable name.'); return; }
  showAI(`Finding variable ${varName}...`);
  speak(`Finding all uses of ${varName}.`);
  try {
    const res  = await fetch('/find-variable-usage', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: getCode(), variable: varName }),
    });
    const data = await res.json();
    if (data.success) {
      const usageList = data.usages.map(u => `Line ${u.line} (${u.type}): ${u.content}`).join('\n');
      out(`Variable '${varName}' (${data.phonetic}):\nFound ${data.count} usages:\n\n${usageList}`);
      speak(`Found ${data.count} usages of ${data.phonetic}.`);
      data.usages.slice(0, 3).forEach(u => speak(`Line ${u.line}: ${u.type}.`));
      if (data.count > 3) data.usages.slice(3).forEach(u => speak(`Line ${u.line}: ${u.type}.`));
      if (data.usages.length > 0) gotoLine(data.usages[0].line, false);
    } else {
      out(data.message); speak(data.message);
    }
  } catch (e) {
    console.error(e); out('Variable search failed.'); speak('Variable search failed.');
  } finally {
    hideAI();
  }
}

// ---------- ERROR BEACON ----------
async function checkSyntaxErrors() {
  // Cancel any prior speech so "checking..." is heard immediately.
  SpeechManager.cancelAll();
  showAI('Checking for errors...');
  speak('Checking code for errors.');
  try {
    const res  = await fetch('/check-syntax', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: getCode() }),
    });
    const data = await res.json();
    if (data.success && !data.has_errors) {
      out('✓ No errors detected. Code looks good!');
      // Cancel the "checking..." utterance so the result speaks cleanly.
      // Without this, Chrome's synth sometimes truncates the second utterance
      // mid-word when transitioning from one queued item to the next.
      stopErrorBeacon();

      speak('No errors detected.');
      speak('Code looks good.');
    } else if (data.success && data.has_errors) {
      const errorList = data.errors.map(e => `Line ${e.line || 'unknown'}: ${e.type} - ${e.message}`).join('\n');
      out(`⚠ Found ${data.error_count} error(s):\n\n${errorList}`);

      // Do NOT cancel speech here.
      // The speech queue already handles sequencing safely now.
      // Canceling here was causing Chrome TTS race conditions
      // where the first utterance cut off the second one.
      speak(`Found ${data.error_count} error${data.error_count !== 1 ? 's' : ''}.`);
      data.errors.forEach(e => speak(`${e.type} on line ${e.line || 'unknown'}.`));

      if (data.errors.length > 0 && data.errors[0].line > 0) {
        ErrorBeaconManager.start(data.errors[0].line, data.errors[0].severity);
        gotoLine(data.errors[0].line, false);
      }
    }
  } catch (e) {
    console.error(e);
    out('Syntax check failed.');

    // Do not cancel queued speech on syntax failure.
    // Just append the failure message normally.
    speak('Syntax check failed.');
  } finally {
    hideAI();
  }
}

function stopErrorBeacon() {
  ErrorBeaconManager.stop();
  window.executionTrace = [];
}

function locateError() { checkSyntaxErrors(); }

// ---------- HELP ----------
async function showHelp() {
  if (!ensureNotExecuting(() => showHelp(), 'show help')) return;
  const lang = getLanguage();
  let msg;
  if (lang === 'hi') {
    msg = 'मुख्य commands: चलाओ कोड चलाने के लिए, कोड समझाओ analysis के लिए, कोड ठीक करो fix के लिए, सारांश दो summary के लिए, लाइन पांच पर जाओ navigate करने के लिए, tutorial खोलने के लिए "tutorial" कहें, "quiz करो" practice के लिए, "bug challenge" debugging के लिए, "मदद और" पूरी list के लिए।';
  } else {
    msg = 'Top commands: run to execute code, analyze for AI review, fix to repair errors, summarize for a quick overview, go to line five to navigate, save snippet to keep your work, tutorial to learn Python, quiz me to practice, bug challenge to debug, sonify block to hear code structure, what variables to list current variables, set inputs to provide input values, night mode to toggle dark theme. Say "more help" for the complete list of every command.';
  }
  out(msg);
  speak(msg);
}

function showFullHelp() {
  if (!ensureNotExecuting(() => showFullHelp(), 'show full help')) return;
  const helpText = `
CODEUP COMMANDS:

EXECUTION:
- "run" or "execute code"
- "analyze code"
- "fix code"
- "summarize this file"

NAVIGATION:
- "go to line [number]"
- "read line [number]"
- "where am I?"
- "go back" / "go forward"

VARIABLES & ERRORS:
- "what variables are available?"
- "find variable [name]"
- "check for errors"
- "where is the error?"

CODE STRUCTURE:
- "sonify block" (Alt+S)
- "read line with context" (Alt+L)

SNIPPETS:
- "save snippet named [name]"
- "load snippet [number]"

EDITING:
- "clear editor"
- "delete line [number]"
- "replace line [N] with [text]"
- "insert function called [name]"
- "insert a for loop"

LEARNING:
- "tutorial" — restart tutorial
- "learning mode" — quiz/mentor mode
- "quiz me on [topic]"
- "explain [concept]"
- "bug challenge"

EXECUTION PLAYBACK:
- "tell the story"
- "next step" / "previous step"
- "set breakpoint at line [N]"
- "watch variable [name]"
- "continue"

UTILITIES:
- "repeat" — repeat last action
- "say that again" — repeat last speech
- "pause voice" — keep mic open but ignore commands
- "resume voice" — start listening again

KEYBOARD:
- Escape: Stop speech
- Ctrl+Enter: Run
- Alt+S/L/V/E/H: Sonify/Line/Vars/Errors/Help
- Alt+Left/Right: Navigate history
- Ctrl+Shift+M: Toggle voice
- Ctrl+Shift+P: Command palette
  `.trim();
  out(helpText);
  const speechText = helpText
    .replace(/[📖🎤💾📊⚠️🎯⚡🔧▶🔍💡↓↑🗺️🔊⏭⏮📋📌🔬❓✓✗]/g, '')
    .replace(/^[A-Z\s&]+:$/gm, '')
    .replace(/\n{2,}/g, '. ')
    .replace(/\n/g, ', ')
    .replace(/\s+/g, ' ')
    .trim();
  speak('Here is the full command list. ' + speechText);
}

function getFileStats() {
  const model = getModel();
  if (!model) return;
  const code  = getCode();
  const stats = `File statistics:\n- ${model.getLineCount()} lines\n- ${code.split(/\s+/).filter(w => w.length > 0).length} words\n- ${code.length} characters`;
  out(stats);
  const lineCount = model.getLineCount();
  const wordCount = code.split(/\s+/).filter(w => w.length > 0).length;
  const charCount = code.length;
  speak(`File has ${lineCount} lines, ${wordCount} words, and ${charCount} characters.`);
}

function goToTop()    { gotoLine(1); speak('Jumped to top of file.'); }
function goToBottom() {
  const model = getModel();
  if (!model) return;
  gotoLine(model.getLineCount());
  speak('Jumped to bottom of file.');
}

function copyCode() {
  if (!ensureNotExecuting(() => copyCode(), 'copy code')) return;
  navigator.clipboard.writeText(getCode()).then(() => {
    speak('Code copied to clipboard.'); out('Code copied to clipboard.');
  }).catch(() => speak('Failed to copy code.'));
}

function pasteCode() {
  if (!ensureNotExecuting(() => pasteCode(), 'paste code')) return;
  navigator.clipboard.readText().then(text => {
    setCode(text); speak('Code pasted from clipboard.'); out('Code pasted from clipboard.');
  }).catch(() => speak('Failed to paste code.'));
}

// ---------- TTS ----------
function speak(text, opts = {}) {
  if (!text) return;
  lastSpokenText = text;
  SpeechManager.enqueue(text, opts).catch(() => {});
}
function speakOutput() {
  if (!ensureNotExecuting(() => speakOutput(), 'speak output')) return;
  const t = document.getElementById('output').textContent || 'No output available.';
  speak(t, { forceFull: true });
}
function repeatLastSpeech() {
  speak(lastSpokenText || 'There is nothing to repeat yet.', { forceFull: true });
}

// ---------- AI BUBBLE ----------
// Always-visible bubble whose contents change. Toggling visibility doesn't
// fire aria-live announcements, but text changes inside an aria-live region
// do — so we just update text and use a placeholder when idle.
function showAI(msg) {
  const b = document.getElementById('aiBubble');
  if (!b) return;
  b.textContent = msg;
  showEl(b);
}
function hideAI() {
  const b = document.getElementById('aiBubble');
  if (!b) return;
  // Set a brief idle message so the live region announces "Idle" rather than
  // appearing to vanish without notice. Then hide visually after a short delay.
  b.textContent = 'Idle.';
  setTimeout(() => hideEl(b), 1500);
}

// ---------- API KEY MODAL ----------
function openApiKeyModal() {
  const modal = document.getElementById('apiKeyModal');
  const input = document.getElementById('apiKeyInput');
  if (!modal) return;
  showEl(modal);
  // Focus the input so screen readers announce the dialog
  requestAnimationFrame(() => {
    if (input) input.focus();
  });
  speak('AI features need a Gemini API key. Get one for free at ai dot google dot dev. Paste it into the field and press Enter, or press Escape to cancel and continue without AI.');
  srAnnounce('Gemini API key required');
}

function closeApiKeyModal() {
  const modal = document.getElementById('apiKeyModal');
  if (modal) hideEl(modal);
  if (editor) editor.focus();
}

async function submitApiKey() {
  const input = document.getElementById('apiKeyInput');
  if (!input) return;
  const key = input.value.trim();
  if (!key) { speak('Please enter a key, or press Escape to cancel.'); return; }

  showAI('Testing API key...');
  speak('Testing your API key.');
  try {
    const res = await fetch('/api-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: key }),
    });
    const data = await res.json();
    if (data.success) {
      input.value = '';
      closeApiKeyModal();
      speak('API key configured. AI features are now available.');
      srAnnounce('API key configured');
    } else {
      speak('That key did not work. ' + (data.error || 'Please try again or press Escape to cancel.'));
    }
  } catch (e) {
    console.error(e);
    speak('Could not configure key. Please check your connection and try again.');
  } finally {
    hideAI();
  }
}

// Detect when the backend says AI is unconfigured and prompt the user once.
function maybePromptForApiKey(responseText) {
  // Pilot mode: deployment uses .env. If the AI says "not configured",
  // tell the user to ask the teacher rather than popping a runtime modal
  // that needs server restart to take effect.
  if (!responseText) return false;
  const lower = String(responseText).toLowerCase();

  // Notice offline-mode prefix and announce it (once per response, not once per session)
  if (lower.startsWith('[offline mode]')) {
    if (!window._offlineModeAnnounced) {
      window._offlineModeAnnounced = true;
      speak('Cloud AI is unavailable. Switching to offline AI for this response.');
      srAnnounce('Offline AI active');
    }
    return false;
  }

  if (window._apiKeyPromptShown) return false;
  if (lower.includes('not configured')) {
    window._apiKeyPromptShown = true;
    speak('AI features are not configured on this server. Please ask your teacher to set the API key, or install Ollama for offline AI.');
    return true;
  }
  if (lower.includes('offline ai is also not available') || lower.includes('offline ai is not available')) {
    if (!window._noAiAnnounced) {
      window._noAiAnnounced = true;
      speak('Both cloud AI and offline AI are unavailable right now. Core features like running code still work. Try again in a minute.');
    }
    return false;
  }
  return false;
}

// ---------- MONACO SETUP ----------
window.MonacoEnvironment = {
  getWorkerUrl: function () { return '/static/python.worker.js'; },
};

require.config({ paths: { vs: '/static/vendor/monaco/min/vs' } });

require(['vs/editor/editor.main'], function () {
  if (editor) { console.warn('Editor already initialized, skipping'); return; }

  editor = monaco.editor.create(document.getElementById('editor'), {
    value:                'print("Hello CodeUp!")',
    language:             'python',
    theme:                document.body.classList.contains('theme-night') ? 'vs-dark' : 'vs',
    fontSize:             16,
    minimap:              { enabled: false },
    automaticLayout:      true,
    // Accessibility — critical for screen reader users
    accessibilitySupport: 'on',
    ariaLabel:            'Python code editor. Use arrow keys to navigate, type to edit. Press Escape to stop speech, Control Shift M to toggle voice control, F1 for editor commands.',
    // Slightly larger line height helps screen-reader sync with cursor
    lineHeight:           24,
    // Make sure tabs and tab-trapping work as users expect
    tabSize:              4,
    insertSpaces:         true,
    // Word wrap helps users who navigate by line
    wordWrap:             'on',
  });

  let _structureDebounce = null;
  editor.onDidChangeModelContent(() => {
    clearTimeout(_structureDebounce);
    _structureDebounce = setTimeout(updateStructurePanel, 600);
  });

  window._editorReady = true;
  try { window._resolveEditorReady(); } catch (e) {}
  while (window._editorReadyQueue && window._editorReadyQueue.length) {
    const fn = window._editorReadyQueue.shift();
    try { fn(); } catch (e) { console.warn('editor queued fn failed', e); }
  }

  registerPythonAutocomplete();
  registerEditorShortcuts();
  loadSnippets();
});

function getModel() { return editor && editor.getModel(); }
function getCode()  { return (editor && editor.getValue()) || ''; }
function getLanguage() { return (document.getElementById('languageSelector') || {}).value || 'en'; }

function setCode(v, opts) {
  opts = opts || {};
  if (typeof ErrorBeaconManager !== 'undefined') ErrorBeaconManager.stop();
  if (!opts.preserveSpeech) SpeechManager.cancelAll();
  lastSpokenText = null;
  window.executionTrace = [];
  window.traceIndex = 0;
  // Navigation history points to line numbers in the OLD code. After a setCode,
  // those line numbers may not exist anymore. Clear it so "go back" doesn't
  // jump into invalid territory.
  navigationHistory = [];
  historyIndex = -1;
  // Breakpoints reference lines in the OLD code. Clear them and their decorations
  // so the gutter dots don't end up pointing at unrelated lines.
  if (typeof _breakpoints !== 'undefined') {
    _breakpoints.clear();
    _watchedVars.clear();
    if (editor && typeof _breakpointDecorations !== 'undefined') {
      try { _breakpointDecorations = editor.deltaDecorations(_breakpointDecorations, []); } catch (e) {}
    }
  }
  if (editor) editor.setValue(v);
}

function out(t) { document.getElementById('output').textContent = t; }

// Convenience: write to output panel AND speak it. Removes the boilerplate
// `out(x); speak(x);` pair that appears 30+ times in this file.
function tellUser(text, opts) {
  if (!text) return;
  out(text);
  speak(text, opts || {});
}

// ---------- PENDING ACTIONS ----------
const pendingActions = [];
async function flushPendingActions() {
  while (pendingActions.length) {
    const a = pendingActions.shift();
    try { await a(); } catch (e) { console.error('Pending action failed', e); }
  }
}
function enqueueAfterExecution(fn) {
  pendingActions.push(fn);
  SpeechManager.enqueue('Queued your request; will run after execution completes.');
}
function ensureNotExecuting(actionFn, description) {
  if (AppState.isExecuting) { enqueueAfterExecution(actionFn); return false; }
  return true;
}

// ---------- HEARTBEAT (audio progress indicator) ----------
function startHeartbeat() {
  stopHeartbeat();
  _heartbeatTimer = setInterval(() => {
    // Very soft brief tone — barely audible but present
    SonificationManager.playTone(440, 0.03, 0.025);
  }, 500);
}
function stopHeartbeat() {
  if (_heartbeatTimer) {
    clearInterval(_heartbeatTimer);
    _heartbeatTimer = null;
  }
}

// ---------- LAST ERROR FOR BEGINNER RE-EXPLANATION ----------
let _lastErrorContext = null;  // {code, error, language}

// ---------- RUN ----------
async function runCode() {
  // Live input mode reroutes through the streaming endpoint
  if (_liveInputMode) {
    return runCodeStreaming();
  }

  SpeechManager.cancelAll();

  const codeToCheck = getCode();
  const usesInput = /\binput\s*\(/.test(codeToCheck);
  if (usesInput && _preflightInputs.length === 0) {
    speak('Heads up: your code uses input, but you have not declared any pre-flight inputs. The first input call will fail with a friendly error. To fix: say "set inputs to" followed by your values, or add a magic comment like "hash inputs colon Alice comma 17" at the top of your code, or say "live input mode" to switch to interactive mode.');
    out('⚠ Your code uses input() but no pre-flight inputs are declared.\n\nFix one of these ways:\n  • Say: "set inputs to Alice and 17"\n  • Add at top of code: # inputs: Alice, 17\n  • Say: "live input mode"\n\nRunning anyway — first input() will explain.');
  } else if (usesInput && _preflightInputs.length > 0) {
    speak(`Pre-flight inputs ready: ${_preflightInputs.length} value${_preflightInputs.length === 1 ? '' : 's'}.`);
  }

  AppState.isExecuting = true;
  cueSuccess();
  startHeartbeat();
  const _runMsgOut = getLanguage() === 'hi' ? 'चल रहा है...' : 'Running...';
  const _runMsgSpoken = getLanguage() === 'hi' ? 'कोड चल रहा है।' : 'Running code.';
  const _runMsgAI = getLanguage() === 'hi' ? 'कोड चल रहा है...' : 'Running code...';
  if (!usesInput) out(_runMsgOut);
  showAI(_runMsgAI);
  speak(_runMsgSpoken);
  srAnnounce(_runMsgSpoken);
  try {
    const res = await fetch('/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: getCode(),
        language: getLanguage(),
        inputs: _preflightInputs,
      }),
    });
    const data = await res.json();
    window.executionTrace = data.trace || [];
    window.traceIndex = 0;

    if (data.success) {
      out(data.output);
      cueSuccess();
      ErrorBeaconManager.stop();
      _lastErrorContext = null;

      // Diff narration: only mention if there were changes from the previous run
      const diff = data.diff;
      _lastOutputDiff = diff;
      _lastOutput = data.output || '';

      speak('Program output:');
      speak(data.output);

      if (diff && !diff.identical && diff.total_changes > 0) {
        speak(diff.summary);
      }

      if (data.semantic_issues && data.semantic_issues.length) {
        data.semantic_issues.forEach(e => speak(`${e.category}. ${e.message}`));
      }
      const truncated = (data.trace || []).some(e => e.type === 'overflow');
      if (truncated) {
        speak('Heads up: your code ran more than five thousand steps, so the execution trace was truncated. Story mode and step-by-step playback may be incomplete.');
      }
      if (typeof window._tutorialOnRunSuccess === 'function') {
        setTimeout(function () { window._tutorialOnRunSuccess(); }, 2000);
      }
    } else {
      out('ERROR:\n' + (data.error || ''));
      cueError();
      // Avoid clearing speech here.
      // The queued narration system already handles sequencing.
      // Clearing here could interrupt the spoken error explanation.
      _lastErrorContext = {
        code: getCode(),
        error: data.error || '',
        language: getLanguage(),
      };
      // Don't let "narrate diff" replay an old comparison after an error run.
      _lastOutputDiff = null;
      const errLines = (data.error || '').trim().split('\n').filter(Boolean);
      const lastLine = errLines[errLines.length - 1] || 'Unknown error';
      const lineMatch = (data.error || '').match(/line (\d+)/);
      const lineHint = lineMatch ? ` on line ${lineMatch[1]}` : '';
      speak(`Error${lineHint}: ${lastLine}`);
      srAnnounce('Error in code');
      if (data.explanation) {
        speak(data.explanation);
      }
      if (data.inputs_hint) {
        speak(data.inputs_hint);
      }
    }
  } catch (e) {
    out('System error.'); console.error(e); cueError(); speak('System error.');
  } finally {
    stopHeartbeat();
    AppState.isExecuting = false;
    hideAI();
    await flushPendingActions();
  }
}

// ---------- STREAMING RUN (Mechanism B — live interactive input) ----------
async function runCodeStreaming() {
  SpeechManager.cancelAll();
  AppState.isExecuting = true;
  cueSuccess();
  startHeartbeat();
  out('Running in live input mode...\n');
  showAI('Live run started.');
  speak('Live input mode. I will read prompts as your code asks for them. Say or type your answer.');
  srAnnounce('Live run started');

  try {
    const startRes = await fetch('/run-stream/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: getCode() }),
    });
    const startData = await startRes.json();
    if (!startData.success) {
      stopHeartbeat();
      AppState.isExecuting = false;
      hideAI();
      const msg = startData.error || 'Could not start live run.';
      out(msg);
      speak(msg);
      if (msg.toLowerCase().includes('windows') || msg.toLowerCase().includes('posix')) {
        speak('Switching back to pre-flight input mode.');
        _liveInputMode = false;
        updateInputModeUI();
      }
      return;
    }

    const runId = startData.run_id;
    _activeStreamRun = { runId, awaitingPrompt: null, awaitingResolve: null };

    const url = `/run-stream/${encodeURIComponent(runId)}/stream`;
    const es = new EventSource(url);
    _activeStreamRun.eventSource = es;

    let buffer = '';
    let outputElement = document.getElementById('output');

    es.onmessage = (evt) => {
      let event;
      try { event = JSON.parse(evt.data); } catch { return; }
      if (event.type === 'stdout') {
        buffer += event.text;
        outputElement.textContent = buffer;
        // Speak chunks as they arrive — but only meaningful ones
        const chunk = event.text.trim();
        if (chunk) speak(chunk);
      } else if (event.type === 'stderr') {
        buffer += '[error] ' + event.text;
        outputElement.textContent = buffer;
        const chunk = event.text.trim();
        if (chunk) speak('Error: ' + chunk);
      } else if (event.type === 'input_request') {
        const prompt = event.prompt || 'Input requested';
        _activeStreamRun.awaitingPrompt = prompt;
        speak(`Your code is asking: ${prompt}. Say your answer, or type it in the command box and press Enter.`);
        srAnnounce('Input requested');
        SonificationManager.playTone(800, 0.15, 0.1);
        // Focus the command input so keyboard users can type immediately
        const cmd = document.getElementById('voiceText');
        if (cmd) {
          cmd.placeholder = 'Type your input and press Enter…';
          cmd.focus();
        }
      } else if (event.type === 'done') {
        const cmd = document.getElementById('voiceText');
        if (cmd) cmd.placeholder = 'Voice & typed commands appear here...';
        speak('Run complete.');
        srAnnounce('Run complete');
        es.close();
        stopHeartbeat();
        AppState.isExecuting = false;
        hideAI();
        _lastOutput = buffer;
        _activeStreamRun = null;
      } else if (event.type === 'error') {
        speak('Stream error.');
        es.close();
        stopHeartbeat();
        AppState.isExecuting = false;
        hideAI();
        _activeStreamRun = null;
      }
    };

    es.onerror = () => {
      speak('Connection to live run lost.');
      try { es.close(); } catch (e) {}
      stopHeartbeat();
      AppState.isExecuting = false;
      hideAI();
      _activeStreamRun = null;
    };
  } catch (e) {
    console.error(e);
    stopHeartbeat();
    AppState.isExecuting = false;
    hideAI();
    speak('Live run failed to start.');
  }
}

async function sendStreamingInput(value) {
  if (!_activeStreamRun || !_activeStreamRun.runId) return false;
  if (!_activeStreamRun.awaitingPrompt) {
    speak('Your code is not waiting for input right now.');
    return false;
  }
  try {
    await fetch(`/run-stream/${encodeURIComponent(_activeStreamRun.runId)}/input`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: value }),
    });
    _activeStreamRun.awaitingPrompt = null;
    speak(`Sent: ${value}`);
    return true;
  } catch (e) {
    speak('Failed to send input.');
    return false;
  }
}

// ---------- ANALYZE ----------
async function analyzeCode() {
  cueSuccess(); out('Analyzing...'); showAI('Analyzing code with AI...'); speak('Analyzing code.');
  try {
    const res  = await fetch('/analyze', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: getCode(), language: getLanguage() }),
    });
    const data = await res.json();
    out(data.analysis || 'No analysis.');
    // Check for AI-unavailable messaging before speaking
    maybePromptForApiKey(data.analysis);
    if (data.analysis) {
      const spoken = data.analysis
        .replace(/^\[offline mode\]\s*/i, '')
        .replace(/\s*want a deeper line by line walkthrough\??.*$/i, '')
        .replace(/\s*just say:?\s*analyze deeper\.?\s*$/i, '');
      speak(spoken);
      window._lastAnalyzeContext = { code: getCode(), at: Date.now() };
    } else {
      speak('No analysis available.');
    }
  } catch (e) {
    out('Analyze failed.'); console.error(e); cueError(); speak('Analyze failed.');
  } finally {
    hideAI();
  }
}

async function analyzeDeep() {
  if (!window._lastAnalyzeContext || (Date.now() - window._lastAnalyzeContext.at > 5 * 60 * 1000)) {
    speak('Please run analyze first, then say analyze deeper.');
    return;
  }
  // Use the SAME code that was analyzed briefly. If the user edited since then,
  // the deep analysis should match the brief one — not silently re-analyze new code.
  const codeForDeep = window._lastAnalyzeContext.code;
  const currentCode = getCode();
  if (codeForDeep !== currentCode) {
    SpeechManager.cancelAll();
    speak('Your code has changed since the last analyze. I will analyze the version you originally asked about. Say analyze again to refresh.');
  }
  cueSuccess(); showAI('Going deeper...'); speak('Going line by line.');
  try {
    const res = await fetch('/analyze-deep', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: codeForDeep, language: getLanguage() }),
    });
    const data = await res.json();
    out(data.analysis || 'No deeper analysis.');
    if (data.analysis) speak(data.analysis);
  } catch (e) {
    console.error(e); speak('Deeper analysis failed.');
  } finally {
    hideAI();
  }
}

// ---------- DEMO PRESETS ----------
let _demoPresetsCache = null;
let _demoPresetsCacheAt = 0;
const _DEMO_CACHE_TTL_MS = 5 * 60 * 1000;  // 5 minutes

async function fetchDemoPresets() {
  // Cache with TTL — if presets ever change at runtime we don't get stuck on stale data.
  if (_demoPresetsCache && (Date.now() - _demoPresetsCacheAt) < _DEMO_CACHE_TTL_MS) {
    return _demoPresetsCache;
  }
  try {
    const res = await fetch('/demo-presets');
    const data = await res.json();
    if (data.success) {
      _demoPresetsCache = data.presets;
      _demoPresetsCacheAt = Date.now();
      return data.presets;
    }
  } catch (e) {
    console.error('Failed to load demos:', e);
  }
  return _demoPresetsCache || [];
}

async function listDemos() {
  const presets = await fetchDemoPresets();
  if (!presets.length) {
    tellUser('No demos available.');
    return;
  }
  let display = 'AVAILABLE DEMOS:\n\n';
  presets.forEach((p, i) => {
    display += `${i + 1}. ${p.title} — ${p.description}\n   Say: "demo ${p.id}"\n\n`;
  });
  out(display);
  // Use srAnnounce only — speak() will be heard by the user; double-announcing
  // via screen reader live region causes "5 demos available" to be read twice.
  speak(`There are ${presets.length} demos available.`);
  presets.forEach(p => speak(`${p.title}. ${p.description}. Say "demo ${p.id}" to load it.`));
  speak('Or just say "demo" followed by the name.');
}

async function runDemo(presetId) {
  const presets = await fetchDemoPresets();
  if (!presets.length) {
    speak('Demos are not available right now.');
    return;
  }

  // No preset specified — pick the first one as a default guided experience
  if (!presetId || !presetId.trim()) {
    const first = presets[0];
    speak(`Loading the ${first.title} demo. ${first.description}`);
    await loadDemoById(first.id);
    return;
  }

  // Try to match by id first
  let match = presets.find(p => p.id === presetId.toLowerCase().trim());

  // Then by title (fuzzy: contains). We deliberately don't do
  // needle.includes(p.id) — that over-matches when preset ids are short
  // (e.g. saying "demo show me primes" would match anything whose id is a
  // substring of "show me primes").
  if (!match) {
    const needle = presetId.toLowerCase().trim();
    match = presets.find(p =>
      p.title.toLowerCase().includes(needle) ||
      p.id.toLowerCase().includes(needle)
    );
  }

  if (!match) {
    const names = presets.map(p => p.id).join(', ');
    speak(`I do not know a demo called ${presetId}. Available demos are: ${names}. Say "show demos" for descriptions.`);
    return;
  }

  await loadDemoById(match.id);
}

async function loadDemoById(id) {
  showAI(`Loading demo: ${id}...`);
  try {
    const res = await fetch(`/demo-presets/${encodeURIComponent(id)}`);
    const data = await res.json();
    if (data.success) {
      setCode(data.code, { preserveSpeech: true });
      out(`DEMO LOADED: ${data.title}\n\n${data.description}\n\nPress Ctrl+Enter or say "run" to execute.`);
      speak(`Demo loaded: ${data.title}. ${data.description}.`);
      speak('The code is in the editor. Press Control Enter, or say "run", to execute it. Say "narrate" to hear it line by line first.');
      srAnnounce(`Demo ${data.title} loaded`);
    } else {
      speak(`Could not load demo: ${data.error || 'unknown error'}`);
    }
  } catch (e) {
    console.error(e);
    speak('Demo loading failed.');
  } finally {
    hideAI();
  }
}

// ---------- NARRATE FULL FILE ----------
async function narrateFile() {
  if (!ensureNotExecuting(() => narrateFile(), 'narrate file')) return;
  SpeechManager.cancelAll();
  const code = getCode();
  if (!code.trim()) {
    speak('The editor is empty. There is nothing to narrate.');
    return;
  }
  cueSuccess();
  out('Narrating file...');
  showAI('Narrating the entire file...');
  speak('Narrating the file from start to finish. Press Escape at any time to stop.');
  try {
    const res = await fetch('/narrate-file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, language: getLanguage() }),
    });
    const data = await res.json();
    if (data.success) {
      const prefix = data.truncated
        ? `File has ${data.line_count} lines. Narrating the first 50.\n\n`
        : `File has ${data.line_count} lines.\n\n`;
      out(prefix + data.narration);
      if (data.truncated) {
        speak(`Your file has ${data.line_count} lines. I will narrate the first 50.`);
      }
      speak(data.narration);
      if (data.truncated) {
        speak(`That covers the first 50 lines. There are ${data.line_count - 50} more lines below.`);
      } else {
        speak('Narration complete.');
      }
      srAnnounce('File narration ready');
    } else {
      const msg = data.error || 'Could not narrate file.';
      out(msg);
      speak(msg);
    }
  } catch (e) {
    console.error(e);
    out('Narration failed.');
    speak('Narration failed. Please try again.');
  } finally {
    hideAI();
  }
}

// ---------- SUMMARIZE ----------
async function summarizeFile() {
  cueSuccess(); out('Summarizing file...'); showAI('Summarizing this file...'); speak('Summarizing this file.');
  try {
    const res  = await fetch('/summarize', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: getCode(), language: getLanguage() }),
    });
    const data = await res.json();
    const summary = data.summary || 'No summary generated.';
    out(summary); speak(summary);
  } catch (e) {
    console.error(e); out('Summary failed.'); speak('Summary failed.');
  } finally {
    speak('Task completed.'); hideAI();
  }
}

// ---------- ADVISE ----------
async function adviseCode() {
  cueSuccess(); out('Advising on your code...'); showAI('Generating improvement suggestions...'); speak('Advising on your code.');
  try {
    const res  = await fetch('/advise', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: getCode(), language: getLanguage() }),
    });
    const data = await res.json();
    const advice = data.advice || 'No advice generated.';
    out(advice); speak('Here are some ways you can improve this code.'); speak(advice);
  } catch (e) {
    out('Advice failed.'); console.error(e); cueError(); speak('Advice failed.');
  } finally {
    speak('Task completed.'); hideAI();
  }
}

// ---------- FIX ----------
async function fixCode() {
  const before = getCode();
  cueSuccess(); out('Fixing...'); showAI('Fixing code with AI...'); speak('Fixing code.');
  try {
    const res  = await fetch('/fix', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: before, language: getLanguage() }),
    });
    const data = await res.json();
    if (data.success) {
      setCode(data.code);
      out('Code fixed.'); speak('Code has been fixed.');
      const diffRes  = await fetch('/diff-explain', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ before, after: data.code, language: getLanguage() }),
      });
      const diffData = await diffRes.json();
      if (diffData.explanation) { out(diffData.explanation); speak(diffData.explanation); }
    } else {
      out('Fix failed.'); speak('Fix failed.');
    }
  } catch (e) {
    console.error(e); out('Fix failed.'); speak('Fix failed.');
  } finally {
    hideAI();
  }
}

// ---------- DESCRIBE LINE ----------
async function describeLine(line) {
  showAI('Describing line ' + line); speak('Describing line ' + line);
  try {
    const res  = await fetch('/describe', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: getCode(), line, language: getLanguage() }),
    });
    const data = await res.json();
    if (data.success) { out(data.description); speak(data.description); }
    else { const msg = data.message || 'Describe failed.'; out(msg); speak(msg); }
  } catch (e) {
    out('Describe failed.'); console.error(e); cueError(); speak('Describe failed.');
  } finally {
    hideAI();
  }
}

// ---------- GENERATE CODE ----------
async function generateCode(prompt) {
  if (!prompt) {
    SpeechManager.cancelAll();
    speak('Please provide a description of what you want to generate.');
    return;
  }

  // Cancel any prior speech so the "generating" announcement is heard immediately.
  SpeechManager.cancelAll();

  // Audio cue + visible status + screen reader announcement + spoken status.
  // All four channels so sighted, blind, and screen-reader users each get feedback.
  cueSuccess();
  out('Generating code for: ' + prompt);
  showAI('Generating code for: ' + prompt);
  srAnnounce('Generating code');
  speak('Generating code for ' + prompt + '. One moment please.');

  try {
    const res = await fetch('/generate-code', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ prompt, language: getLanguage() }),
    });
    const data = await res.json();
    if (data.success && data.code) {
      window.executionTrace = []; window.traceIndex = 0;
      // CRITICAL: setCode() calls SpeechManager.cancelAll() internally, which
      // would kill our pending "generating..." utterance AND any follow-up
      // speak() we queue in the same tick. Pass preserveSpeech:true so the
      // user actually hears the success announcement.
      setCode(data.code, { preserveSpeech: true });
      cueSuccess();

      const usesInput = /\binput\s*\(/.test(data.code);
      if (usesInput) {
        const inputCount = (data.code.match(/\binput\s*\(/g) || []).length;
        out(`Code generated with ${inputCount} input() call${inputCount === 1 ? '' : 's'}.\n\nBefore running, declare your inputs by saying:\n  "set inputs to value1 and value2"`);
        srAnnounce('Code generated');
        speak(`Code is ready. Heads up: it uses input ${inputCount} time${inputCount === 1 ? '' : 's'}. Before pressing run, say "set inputs to" followed by your values.`);
      } else {
        out('Code generated and inserted into editor. Press Control Enter to run, or say "analyze" to hear an explanation.');
        srAnnounce('Code generated');
        speak('Code is ready in the editor. Press Control Enter to run it, or say "walk through code" to hear it explained.');
      }
    } else {
      const reason = data.error || 'the AI returned an empty response. Please try rephrasing your request.';
      out('Code generation failed: ' + reason);
      cueError();
      srAnnounce('Code generation failed');
      speak('Code generation did not work. ' + reason);
    }
  } catch (e) {
    console.error(e);
    out('Code generation failed.');
    cueError();
    srAnnounce('Code generation failed');
    speak('Code generation failed.');
  } finally {
    hideAI();
  }
}

// ---------- NAVIGATION ----------
function gotoLine(line, record = true) {
  if (!ensureNotExecuting(() => gotoLine(line, record), 'go to line')) return;
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const maxLine = model.getLineCount();
  if (line < 1 || line > maxLine) { const msg = `Line ${line} is out of range. File has ${maxLine} lines.`; out(msg); speak(msg); return; }
  if (record) recordNavigation(line);
  try {
    editor.setPosition({ lineNumber: line, column: 1 });
  } catch (e) { console.warn('gotoLine: setPosition failed', e); return; }
  editor.revealLineInCenter(line);
  const text = model.getLineContent(line);
  out(`Line ${line}: ${text}`);
  SpeechManager.cancelAll();
  speak(`Moved to line ${line}. ${text || 'Empty line.'}`);
}

function readLine(line) {
  if (!ensureNotExecuting(() => readLine(line), 'read line')) return;
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const maxLine = model.getLineCount();
  if (line < 1 || line > maxLine) { const msg = `Line ${line} is out of range. File has ${maxLine} lines.`; out(msg); speak(msg); return; }
  SpeechManager.cancelAll();
  const text = model.getLineContent(line);
  out(`Line ${line}: ${text}`);
  speak(`Line ${line}: ${text || 'Empty line.'}`);
}

function readCurrentLine() {
  if (!ensureNotExecuting(() => readCurrentLine(), 'read current line')) return;
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const pos  = editor.getPosition() || { lineNumber: 1 };
  SpeechManager.cancelAll();
  const text = model.getLineContent(pos.lineNumber);
  out(`Line ${pos.lineNumber}: ${text}`);
  speak(`Current line ${pos.lineNumber}: ${text || 'Empty line.'}`);
}

function nextLine() {
  if (!ensureNotExecuting(() => nextLine(), 'next line')) return;
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const pos  = editor.getPosition() || { lineNumber: 1 };
  const line = Math.min(model.getLineCount(), pos.lineNumber + 1);
  SpeechManager.cancelAll();
  editor.setPosition({ lineNumber: line, column: 1 });
  editor.revealLineInCenter(line);
  const text = model.getLineContent(line);
  out(`Line ${line}: ${text}`);
  speak(`Line ${line}: ${text || 'Empty line.'}`);
}

function prevLine() {
  if (!ensureNotExecuting(() => prevLine(), 'previous line')) return;
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const pos  = editor.getPosition() || { lineNumber: 1 };
  const line = Math.max(1, pos.lineNumber - 1);
  SpeechManager.cancelAll();
  editor.setPosition({ lineNumber: line, column: 1 });
  editor.revealLineInCenter(line);
  const text = model.getLineContent(line);
  out(`Line ${line}: ${text}`);
  speak(`Line ${line}: ${text || 'Empty line.'}`);
}

// ---------- EDITING ----------
function clearEditor() {
  // Full reset including navigation history on explicit user clear
  navigationHistory = [];
  historyIndex = -1;
  setCode('');
  out('Editor cleared.');
  speak('Editor cleared. Previous code erased.');
}

function deleteLine(line) {
  const model = getModel();
  if (!model) return;
  const maxLine = model.getLineCount();
  if (line < 1 || line > maxLine) { const msg = `Line ${line} is out of range.`; out(msg); speak(msg); return; }
  const text = model.getLineContent(line);

  // Handle last line correctly: delete from end of previous line to end of last line
  let range;
  if (line === maxLine && maxLine > 1) {
    const prevLen = model.getLineContent(maxLine - 1).length;
    range = new monaco.Range(maxLine - 1, prevLen + 1, maxLine, text.length + 1);
  } else {
    range = new monaco.Range(line, 1, Math.min(line + 1, maxLine + 1), 1);
  }

  model.pushEditOperations([], [{ range, text: '' }], () => null);
  out(`Deleted line ${line}: ${text}`);
  speak(`Deleted line ${line}.`);
}

// ---------- SNIPPETS ----------
function srAnnounce(msg) {
  const el = document.getElementById('srAnnouncer');
  if (!el) return;
  // Clear then set forces screen readers to re-announce even if text is same
  el.textContent = '';
  setTimeout(function () { el.textContent = msg; }, 50);
}

async function saveSnippet() {
  // Keep old function as fallback but redirect to accessible version
  await saveSnippetAccessible();
}

async function saveSnippetAccessible(voiceName) {
  const input = document.getElementById('snippetNameInput');
  const name  = voiceName || (input && input.value.trim()) || 'Untitled';
  await saveSnippetWithName(name);
  if (input) input.value = '';
  srAnnounce('Snippet saved: ' + name);
}

async function saveSnippetWithName(name) {
  await fetch('/snippets', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ name, code: getCode() }),
  });
  await loadSnippets();
  speak(`Snippet saved as ${name}.`);
}

let _loadSnippetsQueued = false;
async function loadSnippets() {
  if (_loadingSnippets) {
    // Mark a refresh as needed; the in-flight call will pick it up when it finishes.
    _loadSnippetsQueued = true;
    return;
  }
  _loadingSnippets = true;
  const list = document.getElementById('snippetList');
  if (!list) { _loadingSnippets = false; return; }
  try {
    const res  = await fetch('/snippets');
    const data = await res.json();
    snippetsCache = data.snippets || [];

    const fragment = document.createDocumentFragment();
    snippetsCache.forEach(sn => {
      const div = document.createElement('div');
      div.className  = 'snippet-item';
      div.textContent = sn.name || 'Untitled Snippet';
      div.dataset.id  = sn.id;
      div.setAttribute('tabindex', '0');
      div.setAttribute('role', 'button');
      div.setAttribute('aria-label', `Load snippet: ${sn.name || 'Untitled'}`);
      div.addEventListener('click',   () => setCode(sn.code));
      div.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setCode(sn.code); } });
      fragment.appendChild(div);
    });

    list.innerHTML = '';
    list.appendChild(fragment);
  } finally {
    _loadingSnippets = false;
    if (_loadSnippetsQueued) {
      _loadSnippetsQueued = false;
      // Recurse to handle the queued refresh
      loadSnippets();
    }
  }
}

async function loadSnippetById(id) {
  const sn = snippetsCache.find(s => String(s.id) === String(id));
  if (!sn) { speak(`Snippet ${id} not found.`); out(`Snippet ${id} not found.`); return; }
  setCode(sn.code); speak(`Loaded snippet ${id}: ${sn.name}.`); out(`Loaded snippet ${id}: ${sn.name}.`);
}

async function deleteSnippetById(id) {
  await fetch(`/snippets/${id}`, { method: 'DELETE' });
  await loadSnippets();
  speak(`Deleted snippet ${id}.`); out(`Deleted snippet ${id}.`);
}

async function renameSnippetById(id, newName) {
  await fetch(`/snippets/${id}`, {
    method:  'PUT',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ name: newName }),
  });
  await loadSnippets();
  speak(`Renamed snippet ${id} to ${newName}.`); out(`Renamed snippet ${id} to ${newName}.`);
}

async function previewSnippetById(id) {
  // Read first 5 lines aloud WITHOUT loading the snippet into the editor.
  // Lets the user audit a snippet before destroying their current work.
  if (!id) { speak('Please specify which snippet to preview.'); return; }
  const sn = snippetsCache.find(s => String(s.id) === String(id) ||
                                      (s.name && s.name.toLowerCase() === String(id).toLowerCase()));
  if (!sn) {
    speak(`I could not find a snippet matching ${id}. Say list snippets to hear what is saved.`);
    return;
  }
  const lines = (sn.code || '').split('\n').slice(0, 5);
  out(`PREVIEW: ${sn.name}\n\n${lines.join('\n')}${(sn.code || '').split('\n').length > 5 ? '\n...' : ''}`);
  speak(`Preview of ${sn.name}. First ${lines.length} line${lines.length === 1 ? '' : 's'}:`);
  lines.forEach((l, i) => speak(`Line ${i + 1}: ${l || 'empty line'}`));
  speak('Say load snippet ' + sn.name + ' to open it in the editor.');
  srAnnounce('Snippet previewed');
}

// ---------- COMMAND HANDLER ----------
async function handleConfirmedAction(action, payload) {
  // Most actions should interrupt previous narration, but some need it to finish first.
  // Generate, analyze, walk: they speak feedback BEFORE the long async wait, don't kill it.
  const _noCancelActions = new Set(['generate_code', 'analyze', 'analyze_deep', 'fix', 'summarize', 'narrate_file', 'walk_through', 'advise', 'story_mode']);
  if (!_noCancelActions.has(action)) {
    SpeechManager.cancelAll();
  }
  if (action === 'run')              await runCode();
  else if (action === 'analyze')     await analyzeCode();
  else if (action === 'walk_through')       await walkThroughCode();
  else if (action === 'analyze_deep') await analyzeDeep();
  else if (action === 'fix')         await fixCode();
  else if (action === 'stop_everything') {
    SpeechManager.cancelAll();
    SonificationManager.clearAll();
    ErrorBeaconManager.stop();
    if (typeof _walkActive !== 'undefined') _walkActive = false;
    out('Stopped.');
    SonificationManager.playTone(400, 0.08, 0.08);
  }
  else if (action === 'speak')       speakOutput();
  else if (action === 'read_output') speakOutput();
  else if (action === 'describe_line') await describeLine(payload && payload.line ? payload.line : 1);
  else if (action === 'next_step' || action === 'previous_step' || action === 'what_changed') {
    const text = (payload && (payload.speech || payload.message)) || 'No trace event available.';
    out(text); speak(text);
  }
  else if (action === 'generate_code') await generateCode(payload && payload.prompt ? payload.prompt : '');
  else if (action === 'save_snippet_named') await saveSnippetAccessible(payload && payload.name ? payload.name : 'Untitled');
  else if (action === 'load_snippet')    await loadSnippetById(payload && payload.id);
  else if (action === 'delete_snippet')  await deleteSnippetById(payload && payload.id);
  else if (action === 'rename_snippet')  await renameSnippetById(payload && payload.id, payload && payload.new_name ? payload.new_name : 'Renamed');
  else if (action === 'preview_snippet') await previewSnippetById(payload && payload.snippet_id);
  else if (action === 'goto_line')       gotoLine(payload && payload.line ? payload.line : 1);
  else if (action === 'read_line')       readLine(payload && payload.line ? payload.line : 1);
  else if (action === 'read_current_line') readCurrentLine();
  else if (action === 'next_line')       nextLine();
  else if (action === 'prev_line')       prevLine();
  else if (action === 'clear_editor')    clearEditor();
  else if (action === 'delete_line')     deleteLine(payload && payload.line ? payload.line : 1);
  else if (action === 'summarize')       await summarizeFile();
  else if (action === 'narrate_file')    await narrateFile();
  else if (action === 'demo_list')       await listDemos();
  else if (action === 'demo_run')        await runDemo(payload && payload.preset ? payload.preset : '');
  else if (action === 'pause_voice')     pauseVoiceRecognition();
  else if (action === 'resume_voice')    resumeVoiceRecognition();
  else if (action === 'advise')          await adviseCode();
  else if (action === 'read_line_enhanced') await readLineEnhanced(payload && payload.line ? payload.line : (editor && editor.getPosition() ? editor.getPosition().lineNumber : 1));
  else if (action === 'sonify_block')    await sonifyCurrentBlock();
  else if (action === 'sonify_function') await sonifyFunction(payload && payload.function_name ? payload.function_name : '');
  else if (action === 'sonify_class')    await sonifyClass(payload && payload.class_name ? payload.class_name : '');
  else if (action === 'find_function')   speak('Find function: ' + (payload && payload.function_name ? payload.function_name : ''));
  else if (action === 'find_class')      speak('Find class: ' + (payload && payload.class_name ? payload.class_name : ''));
  else if (action === 'show_structure')  toggleStructurePanel();
  else if (action === 'list_variables')  await listVariables();
  else if (action === 'find_variable')   await findVariable(payload && payload.variable ? payload.variable : '');
  else if (action === 'check_errors')    await checkSyntaxErrors();
  else if (action === 'locate_error')    locateError();
  else if (action === 'stop_beacon')     { stopErrorBeacon(); speak('Error beacon stopped.'); }
  else if (action === 'go_back')         navigateBack();
  else if (action === 'go_forward')      navigateForward();
  else if (action === 'show_history')    showNavigationHistory();
  else if (action === 'help')            showHelp();
  else if (action === 'more_help')       showFullHelp();
  else if (action === 'file_stats')      getFileStats();
  else if (action === 'go_to_top')       goToTop();
  else if (action === 'go_to_bottom')    goToBottom();
  else if (action === 'copy_code')       copyCode();
  else if (action === 'paste_code')         pasteCode();
  else if (action === 'restart_tutorial')   restartTutorial();
  else if (action === 'toggle_dyslexia')    { document.getElementById('dyslexiaToggle').click(); }
  else if (action === 'toggle_motion')      { document.getElementById('motionToggle').click(); }
  else if (action === 'toggle_night')       { document.getElementById('nightToggle').click(); }
  else if (action === 'cycle_color_mode')   {
    const s = document.getElementById('colorVisionMode');
    s.selectedIndex = (s.selectedIndex + 1) % s.options.length;
    s.dispatchEvent(new Event('change'));
  }
  else if (action === 'set_color_mode') {
    const s = document.getElementById('colorVisionMode');
    if (!s) { speak('Color mode selector not found.'); return; }
    const mode = (payload && payload.mode) || 'default';
    // Find the option whose value matches the requested mode
    let found = false;
    for (let i = 0; i < s.options.length; i++) {
      if (s.options[i].value === mode) {
        s.selectedIndex = i;
        s.dispatchEvent(new Event('change'));
        found = true;
        break;
      }
    }
    if (!found) {
      speak(`Color mode "${mode}" not recognized. Try protanopia, deuteranopia, tritanopia, high contrast, or default.`);
    }
  }
  else if (action === 'list_variables_voice') await listVariablesWithValues();
  else if (action === 'start_tutorial')     { if (window.TutorialController) window.TutorialController.open(); }
  else if (action === 'skip_tutorial')      { if (window.TutorialController) window.TutorialController.close(); }
  else if (action === 'tutorial_next')      { if (window.TutorialController && window.TutorialController.active) window.TutorialController.next(); }
  else if (action === 'insert_function')    insertFunctionVoice(payload && payload.function_name);
  else if (action === 'insert_class')       insertClassVoice(payload && payload.class_name);
  else if (action === 'insert_loop')        insertLoopVoice(payload && payload.loop_var, payload && payload.iterable);
  else if (action === 'insert_if')          insertIfVoice(payload && payload.condition);
  else if (action === 'append_line')        appendLineVoice(payload && payload.text);
  else if (action === 'replace_line')       replaceLineVoice(payload && payload.line_number, payload && payload.text);
  else if (action === 'insert_line')        insertLineVoice(payload && payload.line_number, payload && payload.text);
  else if (action === 'add_parameter')      addParameterVoice(payload && payload.param_name, payload && payload.function_name);
  else if (action === 'suggest_next')       await suggestNextLine();
  else if (action === 'choose_suggestion')  chooseSuggestion(payload && payload.choice);
  else if (action === 'story_mode')         await tellExecutionStory();
  else if (action === 'set_breakpoint')     setBreakpoint(payload && payload.line_number);
  else if (action === 'clear_breakpoints')  clearBreakpoints();
  else if (action === 'watch_variable')     watchVariable(payload && payload.variable);
  else if (action === 'debug_continue')     debugContinue();
  else if (action === 'debug_step_in')      speak('Step in is not yet supported in sandbox mode.');
  else if (action === 'debug_step_out')     speak('Step out is not yet supported in sandbox mode.');
  else if (action === 'mentor_mode')        startMentorMode();
  else if (action === 'quiz_me')            await quizMe(payload && payload.topic);
  else if (action === 'explain_concept')    await explainConcept(payload && payload.concept);
  else if (action === 'bug_challenge')      await bugChallenge();
  // Pre-flight inputs
  else if (action === 'set_inputs')         setPreflightInputs(payload && payload.values);
  else if (action === 'clear_inputs')       clearPreflightInputs();
  else if (action === 'list_inputs')        listPreflightInputs();
  else if (action === 'live_input_mode')    enableLiveInputMode();
  else if (action === 'preflight_input_mode') enablePreflightInputMode();
  // Voice macros
  else if (action === 'save_macro')         await saveMacro(payload && payload.name);
  else if (action === 'use_macro')          await useMacro(payload && payload.name);
  else if (action === 'list_macros')        await listMacrosVoice();
  // Output bookmarks
  else if (action === 'bookmark_output')    await bookmarkOutput(payload && payload.label);
  else if (action === 'read_bookmark')      await readBookmark(payload && payload.label);
  else if (action === 'list_bookmarks')     await listBookmarks();
  // Live execution position
  else if (action === 'where_am_i')         await reportPosition();
  // Beginner-mode error explanation
  else if (action === 'explain_simply')     await explainErrorSimply();
  // Output diff narration
  else if (action === 'narrate_diff')       narrateOutputDiff();
}

// ---------- PRE-FLIGHT INPUTS ----------
function setPreflightInputs(values) {
  if (!Array.isArray(values) || values.length === 0) {
    speak('No values heard. Try saying "set inputs to" followed by your values separated by "and" or commas.');
    return;
  }
  _preflightInputs = values.map(v => String(v));
  updateInputsPanel();
  const summary = _preflightInputs.join(', ');
  speak(`${_preflightInputs.length} input${_preflightInputs.length === 1 ? '' : 's'} ready: ${summary}.`);
  out(`PRE-FLIGHT INPUTS SET (${_preflightInputs.length}):\n${_preflightInputs.map((v, i) => `  ${i + 1}. ${v}`).join('\n')}\n\nThese will be used in order when your code calls input().`);
  srAnnounce(`${_preflightInputs.length} inputs set`);
}

function clearPreflightInputs() {
  _preflightInputs = [];
  updateInputsPanel();
  speak('Pre-flight inputs cleared.');
  out('Pre-flight inputs cleared.');
  srAnnounce('Inputs cleared');
}

function listPreflightInputs() {
  if (_preflightInputs.length === 0) {
    speak('You have no pre-flight inputs declared.');
    out('No pre-flight inputs declared.');
    return;
  }
  speak(`You have ${_preflightInputs.length} input${_preflightInputs.length === 1 ? '' : 's'}:`);
  _preflightInputs.forEach((v, i) => speak(`Input ${i + 1}: ${v}.`));
  out(`PRE-FLIGHT INPUTS (${_preflightInputs.length}):\n${_preflightInputs.map((v, i) => `  ${i + 1}. ${v}`).join('\n')}`);
}

function enableLiveInputMode() {
  _liveInputMode = true;
  updateInputModeUI();
  speak('Switched to live input mode. When you press run, your code will pause and ask for each input as it needs it. Note: live mode requires Linux or macOS on the server.');
  out('LIVE INPUT MODE ON\n\nYour code will pause at each input() call and wait for you to answer by voice or by typing in the command box.');
  srAnnounce('Live input mode on');
}

function enablePreflightInputMode() {
  _liveInputMode = false;
  updateInputModeUI();
  speak('Switched to pre-flight input mode. Declare your inputs ahead of time, then press run.');
  out('PRE-FLIGHT INPUT MODE ON (default)\n\nDeclare inputs first: say "set inputs to value1 and value2", then press run.');
  srAnnounce('Pre-flight input mode on');
}

function updateInputModeUI() {
  const indicator = document.getElementById('inputModeIndicator');
  if (indicator) {
    indicator.textContent = _liveInputMode ? '⚡ LIVE' : '📋 PRE-FLIGHT';
    indicator.title = _liveInputMode
      ? 'Live input mode: your code pauses and asks for inputs in real time.'
      : 'Pre-flight input mode: inputs are declared ahead of time.';
  }
}

function updateInputsPanel() {
  const panel = document.getElementById('inputsPanelList');
  if (!panel) return;
  if (_preflightInputs.length === 0) {
    panel.innerHTML = '<div style="color:var(--text-dim);font-style:italic;padding:6px 0;font-size:0.8rem;">No inputs declared</div>';
    return;
  }
  panel.innerHTML = _preflightInputs.map((v, i) =>
    `<div class="snippet-item" style="font-size:0.8rem;padding:6px 10px;"><span>${i + 1}. ${escapeHtml(v)}</span></div>`
  ).join('');
}

// ---------- VOICE MACROS ----------
async function saveMacro(name) {
  if (!name) { speak('Please give the macro a name. Say "remember this as" followed by a name.'); return; }
  const code = getCode();
  if (!code.trim()) { speak('The editor is empty. Nothing to save as a macro.'); return; }
  try {
    const res = await fetch('/macros', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, code }),
    });
    const data = await res.json();
    if (data.success) {
      speak(data.speech || `Macro ${name} saved.`);
      srAnnounce(`Macro ${name} saved`);
    } else {
      speak(data.error || 'Could not save macro.');
    }
  } catch (e) {
    speak('Macro save failed.');
  }
}

async function useMacro(name) {
  if (!name) { speak('Which macro? Say "use macro" followed by the name.'); return; }
  try {
    const res = await fetch(`/macros/get/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (data.success) {
      setCode(data.code);
      speak(`Loaded macro ${name}.`);
      out(`Macro "${name}" loaded into the editor.`);
      srAnnounce(`Macro ${name} loaded`);
    } else {
      speak(`No macro named ${name}. Say "list macros" to hear what is saved.`);
    }
  } catch (e) {
    speak('Macro load failed.');
  }
}

async function listMacrosVoice() {
  try {
    const res = await fetch('/macros');
    const data = await res.json();
    if (!data.success) { speak('Could not list macros.'); return; }
    speak(data.speech);
    if (data.names && data.names.length) {
      out(`MACROS (${data.names.length}):\n${data.names.map((n, i) => `  ${i + 1}. ${n}`).join('\n')}\n\nSay "use macro" followed by a name.`);
    } else {
      out('No macros saved. Save one by writing code, then saying "remember this as" followed by a name.');
    }
  } catch (e) {
    speak('Macro list failed.');
  }
}

// ---------- OUTPUT BOOKMARKS ----------
async function bookmarkOutput(label) {
  const outputEl = document.getElementById('output');
  const position = outputEl ? (outputEl.textContent || '').length : 0;
  try {
    const res = await fetch('/bookmarks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label: label || '', position }),
    });
    const data = await res.json();
    if (data.success) {
      SonificationManager.playTone(750, 0.08, 0.08);
      speak(data.speech);
      srAnnounce('Bookmark saved');
    }
  } catch (e) {
    speak('Could not save bookmark.');
  }
}

async function readBookmark(label) {
  if (!label) {
    // Read from most recent
    const res = await fetch('/bookmarks');
    const data = await res.json();
    if (!data.success || !data.bookmarks.length) {
      speak('No bookmarks saved.');
      return;
    }
    label = data.bookmarks[data.bookmarks.length - 1].label;
  }
  const outputEl = document.getElementById('output');
  const fullOutput = outputEl ? outputEl.textContent : '';
  try {
    const res = await fetch('/bookmarks/read', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ label, output: fullOutput }),
    });
    const data = await res.json();
    if (data.success) {
      speak(`Reading from bookmark ${data.label}.`);
      speak(data.slice || 'Empty.');
    } else {
      speak(data.error || 'Bookmark not found.');
    }
  } catch (e) {
    speak('Could not read from bookmark.');
  }
}

async function listBookmarks() {
  try {
    const res = await fetch('/bookmarks');
    const data = await res.json();
    if (!data.success) { speak('Could not list bookmarks.'); return; }
    if (!data.bookmarks.length) {
      speak('You have no bookmarks.');
      out('No bookmarks. Say "bookmark this" while output is showing to save one.');
      return;
    }
    speak(`You have ${data.bookmarks.length} bookmark${data.bookmarks.length === 1 ? '' : 's'}:`);
    data.bookmarks.forEach(b => speak(b.label));
    out(`BOOKMARKS (${data.bookmarks.length}):\n${data.bookmarks.map((b, i) => `  ${i + 1}. ${b.label}`).join('\n')}`);
  } catch (e) {
    speak('Bookmark list failed.');
  }
}

// ---------- LIVE EXECUTION POSITION ----------
async function reportPosition() {
  if (_activeStreamRun && _activeStreamRun.runId) {
    try {
      const res = await fetch(`/run-stream/${encodeURIComponent(_activeStreamRun.runId)}/position`);
      const data = await res.json();
      if (data.success && data.alive) {
        const sec = (data.elapsed_ms / 1000).toFixed(1);
        if (data.awaiting_input) {
          speak(`Your code has been running for ${sec} seconds and is waiting for your input.`);
        } else {
          speak(`Your code has been running for ${sec} seconds.`);
        }
        return;
      }
    } catch (e) {}
  }
  // Fall back to breadcrumb at cursor
  await readBreadcrumb();
}

async function readBreadcrumb() {
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const pos = editor.getPosition() || { lineNumber: 1 };
  try {
    const res = await fetch('/breadcrumbs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: getCode(), line: pos.lineNumber }),
    });
    const data = await res.json();
    if (data.success) {
      speak(`You are in: ${data.breadcrumb}.`);
      out(`Position: ${data.breadcrumb}`);
    } else {
      speak(data.message || 'Could not determine position.');
    }
  } catch (e) {
    speak('Position lookup failed.');
  }
}

// ---------- BEGINNER ERROR EXPLANATION ----------
async function explainErrorSimply() {
  if (!_lastErrorContext) {
    speak('There is no recent error to explain. Run your code first.');
    return;
  }
  showAI('Explaining in simpler terms...');
  speak('Let me explain that more simply.');
  try {
    const res = await fetch('/explain-error-beginner', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(_lastErrorContext),
    });
    const data = await res.json();
    if (data.success) {
      out(data.explanation);
      speak(data.explanation);
      srAnnounce('Beginner explanation ready');
    } else {
      speak('Could not generate a simpler explanation.');
    }
  } catch (e) {
    speak('Explanation failed.');
  } finally {
    hideAI();
  }
}

// ---------- OUTPUT DIFF NARRATION ----------
function narrateOutputDiff() {
  if (!_lastOutputDiff) {
    speak('No diff available. Run your code at least twice to compare outputs.');
    return;
  }
  if (_lastOutputDiff.identical) {
    speak('The output is identical to the previous run.');
    return;
  }
  if (!_lastOutputDiff.changed_lines || _lastOutputDiff.changed_lines.length === 0) {
    speak(_lastOutputDiff.summary || 'First run — nothing to compare yet.');
    return;
  }
  speak(_lastOutputDiff.summary);
  _lastOutputDiff.changed_lines.forEach(c => {
    if (c.kind === 'added') speak(`Line ${c.line_no}, added: ${c.after}.`);
    else if (c.kind === 'removed') speak(`Line ${c.line_no}, removed: ${c.before}.`);
    else speak(`Line ${c.line_no}, was "${c.before}", now "${c.after}".`);
  });
}

function tryResolveConfirmation(txt) {
  if (!pendingConfirm) return false;
  if (pendingConfirm.expiresAt && Date.now() > pendingConfirm.expiresAt) {
    pendingConfirm = null;
    return false;  // let the new command flow through normally
  }
  const options = pendingConfirm.options || [];
  const lower   = txt.toLowerCase().trim();

  // 1. Explicit cancel — user wants out
  const cancelWords = ['cancel', 'no', 'neither', 'nope', 'none', 'forget it',
                       'never mind', 'nevermind', 'skip',
                       'नहीं', 'रद्द करो', 'छोड़ो'];
  if (cancelWords.some(w => lower === w)) {
    pendingConfirm = null;
    speak('Cancelled.');
    return true;
  }

  // 2. Exact match on one of the offered options — clear yes
  for (const opt of options) {
    if (lower === opt || lower === opt.replace(/_/g, ' ')) {
      pendingConfirm = null;
      speak('Got it. ' + opt.replace(/_/g, ' ') + '.');
      handleConfirmedAction(opt, pendingConfirm && pendingConfirm.context || {});
      return true;
    }
  }

  // 3. "First" / "second" / "1" / "2" — positional choice
  const positionalMap = {
    'first': 0, '1': 0, 'one': 0, 'option one': 0, 'option 1': 0,
    'second': 1, '2': 1, 'two': 1, 'option two': 1, 'option 2': 1,
    'पहला': 0, 'दूसरा': 1, 'एक': 0, 'दो': 1,
  };
  if (positionalMap.hasOwnProperty(lower) && positionalMap[lower] < options.length) {
    const chosen = options[positionalMap[lower]];
    pendingConfirm = null;
    speak('Got it. ' + chosen.replace(/_/g, ' ') + '.');
    handleConfirmedAction(chosen, {});
    return true;
  }

  // 4. The user said something NEW that doesn't match the options or cancel.
  //    Don't trap them — clear the pending confirm and let the new utterance
  //    flow through as a fresh command. This is the bug fix: previously the
  //    user was stuck repeating themselves until timeout.
  pendingConfirm = null;
  speak('Okay, listening for a new command.');
  return false;  // signal that the caller should re-route this text
}

async function handleCommandText(txt) {
  const field = document.getElementById('voiceText');
  if (field) field.value = txt;

  // Quiz answer intercept (mirrors handleVoiceCommand) — per-tab state
  const _ts = tabState();
  if (_ts._pendingQuizAnswer) {
    if (_ts._pendingQuizAnswer.expiresAt && Date.now() > _ts._pendingQuizAnswer.expiresAt) {
      _ts._pendingQuizAnswer = null;
    }
  }
  if (_ts._pendingQuizAnswer) {
    const t = txt.toLowerCase().trim();
    const match = t.match(/(?:answer|option|choose)\s+([abcd])|^([abcd])$/);
    if (match) {
      const q = _ts._pendingQuizAnswer;
      _ts._pendingQuizAnswer = null;
      const chosen = (match[1] || match[2]).toUpperCase();
      if (chosen === q.answer) {
        SonificationManager.playTone(900, 0.1, 0.1);
        speak(`Correct! ${q.explanation}`);
        srAnnounce('Correct answer');
        out(`✓ CORRECT!\n\n${q.explanation}`);
      } else {
        SonificationManager.playTone(200, 0.15, 0.08);
        speak(`Not quite. The correct answer was ${q.answer}. ${q.explanation}`);
        srAnnounce('Wrong answer');
        out(`✗ The correct answer was ${q.answer}.\n\n${q.explanation}`);
      }
      return;
    }
  }

  // Bug challenge intercept (mirrors handleVoiceCommand) — per-tab state
  if (_ts._pendingBugChallenge) {
    if (_ts._pendingBugChallenge.expiresAt && Date.now() > _ts._pendingBugChallenge.expiresAt) {
      _ts._pendingBugChallenge = null;
    }
  }
  if (_ts._pendingBugChallenge) {
    const t = txt.toLowerCase().trim();
    if (t.includes('show answer') || t.includes('give up') || t.includes('reveal') || t.includes('answer दिखाओ')) {
      const ch = _ts._pendingBugChallenge;
      _ts._pendingBugChallenge = null;
      out(`THE BUG:\n${ch.bug}\n\nFIXED CODE:\n${ch.fixed}`);
      speak(`The bug was: ${ch.bug}`);
      setTimeout(() => setCode(ch.fixed), 2000);
      srAnnounce('Answer revealed');
      return;
    }
  }

  if (pendingConfirm) {
    const handled = tryResolveConfirmation(txt);
    if (handled) return;
    // Confirm was abandoned because the user said something unrelated.
    // Fall through and process txt as a fresh command.
  }

  try {
    const res  = await fetch('/voice-command', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text: txt }),
    });
    const data = await res.json();

    if (!data.success) { speak(data.message || 'Command not recognized.'); return; }

    const action = data.action;

    if (action === 'unknown') {
      const heard = data.heard || txt;
      speak(`I heard "${heard}", but I could not match it to a command. Say help to hear available commands.`);
      out(`Unrecognized command: "${heard}"`);
      return;
    }

    if (action === 'confirm') {
      const opts = data.options || [];
      pendingConfirm = {
        options:   opts,
        expiresAt: Date.now() + 15000,
        context:   { heard: data.heard || txt, raw: txt },
      };
      const optsSpoken = opts.map(o => o.replace(/_/g, ' ')).join(' or ');
      const heard = data.heard || txt;
      speak(`Did you mean ${optsSpoken}? Say first or second, or just say a new command.`);
      out(`Heard: "${heard}"\nDid you mean: ${optsSpoken}?\nSay "first" / "second", a new command, or "cancel".`);
      return;
    }

    await handleConfirmedAction(action, data);
  } catch (err) {
    console.error(err); speak('Voice command failed.');
  }
}

async function submitCommand() {
  const field = document.getElementById('voiceText');
  if (!field) return;
  const txt = field.value.trim();
  if (!txt) return;
  await handleCommandText(txt);
  field.value = '';
}

// ---------- VOICE ----------
function toggleVoice() {
  // If paused, treat toggle as "unpause and continue".
  if (isListening && _voicePaused) {
    resumeVoiceRecognition();
    return;
  }
  if (isListening) stopListening(); else startListening();
}

function startListening() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    const isFirefox = navigator.userAgent.toLowerCase().includes('firefox');
    const msg = isFirefox
      ? 'Voice input is not supported in Firefox. Please open CodeUp in Chrome or Edge for voice control. Keyboard shortcuts and the typed command box still work in Firefox.'
      : 'Speech recognition is not supported in this browser. Please use Chrome or Edge for voice input. Keyboard shortcuts and the typed command box still work.';
    out(msg);
    speak(msg);
    srAnnounce('Speech recognition unavailable');
    return;
  }
  if (isListening) { speak('Already listening.'); return; }

  recognition = new SR();
  recognition.continuous      = true;
  recognition.interimResults  = false;
  recognition.lang            = getLanguage() === 'hi' ? 'hi-IN' : 'en-US';
  recognition._restartAttempts = 0;
  recognition._maxRestarts     = 5;
  recognition._backoffBase     = 300;

  recognition.onstart = () => {
    isListening = true;
    AppState.isListening = true;
    recognition._restartAttempts = 0;
    _lastRecognitionActivity = Date.now();
    _startRecognitionWatchdog();

    // If paused, keep paused UI on session restart and stay silent
    if (_voicePaused) {
      const btn = document.getElementById('voiceButton');
      if (btn) {
        btn.textContent = '🎤 Voice (Paused)';
        btn.setAttribute('aria-pressed', 'mixed');
        btn.classList.remove('cu-button-voice--active');
        btn.classList.add('cu-button-voice--paused');
      }
      _debugLog('Voice: session restarted while paused — staying silent');
      return;
    }

    const btn = document.getElementById('voiceButton');
    if (btn) {
      btn.textContent = '🎤 Voice (ON)';
      btn.setAttribute('aria-pressed', 'true');
      btn.classList.remove('cu-button-voice--paused');
      btn.classList.add('cu-button-voice--active');
    }

    // Auto-restart from Chrome's idle timeout: silent except for a brief tone
    if (!_voiceStartIsUserInitiated) {
      cueSuccess();
      _debugLog('Voice: silent auto-restart');
      return;
    }
    _voiceStartIsUserInitiated = false;
    cueSuccess();

    const lang = getLanguage();
    const code = getCode();
    const hasCode = code.trim().length > 0;
    const lineCount = code.split('\n').length;

    if (!window._voiceGreetedThisSession) {
      window._voiceGreetedThisSession = true;
      if (lang === 'hi') {
        // Hindi: minimal greeting. Demo testing has been English-only.
        speak('कोड चलाओ कहें।');
      } else {
        speak('Voice on.');
        if (hasCode) {
          speak(`${lineCount} line${lineCount === 1 ? '' : 's'} in the editor.`);
        } else {
          speak('Editor is empty.');
        }
        speak('Say "help" for commands.');
      }
    }
    _debugLog('Voice: Listening started');
  };

  recognition.onresult = async (event) => {
    const transcript = event.results[event.results.length - 1][0].transcript;
    _debugLog('Voice heard:', transcript);
    _lastRecognitionActivity = Date.now();  // any input proves recognition is alive

    // When paused, only listen for the resume keyword. Drop everything else
    // so the user can keep talking (e.g. during a pitch) without triggering
    // commands or appearing in the UI.
    if (_voicePaused) {
      const lower = transcript.toLowerCase().trim();
      // Whitelist of resume phrases. EXACT match only — substring match would
      // resume on "go back to line 5" or "continue running the tests".
      const resumePhrases = new Set([
        'resume', 'resume please',
        'resume voice', 'resume voice recognition', 'resume voice control',
        'resume voice input', 'voice resume',
        'start listening', 'continue listening',
        'unmute', 'wake up', 'come back',
        'are you listening', 'listening',
        'आवाज़ चालू करो', 'voice चालू करो', 'voice resume करो',
        'फिर से सुनो', 'सुनो', 'जागो',
      ]);
      if (resumePhrases.has(lower)) {
        resumeVoiceRecognition();
      } else {
        // Silently drop. Do NOT clear voiceText or output — we want zero UI noise.
        _debugLog('Voice paused — dropped:', transcript);
      }
      return;
    }

    await handleVoiceCommand(transcript);
  };

  recognition.onerror = (event) => {
    console.error('Voice error:', event.error);
    if (event.error === 'no-speech') { return; }
    if (event.error === 'aborted')   { isListening = false; AppState.isListening = false; return; }
    if (event.error === 'audio-capture' || event.error === 'not-allowed') {
      speak('Microphone access blocked. Please grant microphone permission and toggle voice again.');
      isListening = false; AppState.isListening = false; return;
    }
    console.warn('Voice error (will retry):', event.error);
  };

  recognition.onend = () => {
    _debugLog('Voice: Session ended');
    if (!isListening) return;
    recognition._restartAttempts = (recognition._restartAttempts || 0) + 1;
    if (recognition._restartAttempts > 10) {
      recognition._restartAttempts = 0;
    }
    if (_restartTimer) { clearTimeout(_restartTimer); _restartTimer = null; }
    // 400ms cooldown — Chrome throws InvalidStateError if start() is called
    // too soon after onend. 200ms hits the edge case; 400ms is safe.
    _restartTimer = setTimeout(() => {
      _restartTimer = null;
      _voiceStartIsUserInitiated = false;
      try {
        if (isListening) recognition.start();
        // Recognition is alive again — reset the watchdog
        _lastRecognitionActivity = Date.now();
      } catch (e) {
        // Almost always InvalidStateError. Retry with longer waits, and if
        // both retries fail, reconcile state so the user can recover.
        _debugLog('Auto-restart deferred:', e.message);
        setTimeout(() => {
          try {
            if (isListening) recognition.start();
            _lastRecognitionActivity = Date.now();
          }
          catch (e2) {
            _debugLog('Second restart failed:', e2.message);
            // Third and final attempt
            setTimeout(() => {
              try {
                if (isListening) recognition.start();
                _lastRecognitionActivity = Date.now();
              } catch (e3) {
                // Recognition is dead. Stop lying to the user about state.
                _debugLog('Recognition session permanently lost. Reconciling.');
                isListening = false;
                AppState.isListening = false;
                _voicePaused = false;
                const btn = document.getElementById('voiceButton');
                if (btn) {
                  btn.textContent = '🎤 Voice (Off)';
                  btn.setAttribute('aria-pressed', 'false');
                  btn.classList.remove('cu-button-voice--active');
                  btn.classList.remove('cu-button-voice--paused');
                }
                // Audible cue so the user knows something happened
                SonificationManager.playTone(300, 0.15, 0.1);
                speak('Voice recognition stopped unexpectedly. Press the voice button or Control Shift M to restart.');
              }
            }, 3000);
          }
        }, 1500);
      }
    }, 400);
  };

  try {
    _voiceStartIsUserInitiated = true;
    recognition.start();
  } catch (e) {
    console.error('Failed to start recognition:', e);
    speak('Failed to start voice control.');
    isListening = false; AppState.isListening = false;
    _voiceStartIsUserInitiated = false;
  }
}

function stopListening() {
  if (!recognition || !isListening) { speak('Voice control is not active.'); return; }
  if (_restartTimer) { clearTimeout(_restartTimer); _restartTimer = null; }
  _stopRecognitionWatchdog();
  isListening = false;
  AppState.isListening = false;
  // Stopping fully also clears any paused state — next start is a fresh session
  _voicePaused = false;
  try { localStorage.removeItem('codeup_voice_paused'); } catch (e) {}
  const btn = document.getElementById('voiceButton');
  if (btn) {
    btn.textContent = '🎤 Voice (Off)';
    btn.setAttribute('aria-pressed', 'false');
    btn.classList.remove('cu-button-voice--active');
  }
  recognition.stop();
  speak('Voice control deactivated.');
  _debugLog('Voice: Listening stopped');
}

// Pause: keep the mic open so we can hear "resume", but drop every command
// in between. This lets the presenter put on a blindfold and pitch without
// CodeUp reacting to ambient speech.
function pauseVoiceRecognition() {
  if (!isListening) { speak('Voice control is not active.'); return; }
  if (_voicePaused) { speak('Voice is already paused.'); return; }
  _voicePaused = true;
  try { localStorage.setItem('codeup_voice_paused', '1'); } catch (e) {}

  // Reconcile state: if Chrome's recognition silently died, kick it back to
  // life. The pause flag will gate everything until resume.
  if (recognition) {
    try {
      // If recognition is in an indeterminate state, restart it. The onend
      // auto-restart logic will rebuild the session within ~200ms.
      // We do NOT call recognition.stop() here — that would set isListening
      // false and break the user model.
    } catch (e) { /* ignore */ }
  }

  // Visual + ARIA state — the button gets a distinct paused look so a sighted
  // helper can see at a glance that the mic is open but ignoring input.
  const btn = document.getElementById('voiceButton');
  if (btn) {
    btn.textContent = '🎤 Voice (Paused)';
    btn.setAttribute('aria-pressed', 'mixed');
    btn.classList.remove('cu-button-voice--active');
    btn.classList.add('cu-button-voice--paused');
  }

  // Two-tone descending cue so the user gets non-verbal confirmation
  // even if their TTS is interrupted or muted.
  SonificationManager.playTone(700, 0.08, 0.1);
  setTimeout(() => SonificationManager.playTone(500, 0.12, 0.1), 100);

  const lang = getLanguage();
  if (lang === 'hi') {
    speak('Voice रुक गया। बात करते रहें — मैं नहीं सुनूंगा। फिर से शुरू करने के लिए "resume" कहें।');
  } else {
    speak('Voice paused. Talk freely — I will ignore everything until you say "resume".');
  }
  srAnnounce('Voice paused');
  _debugLog('Voice: Paused');
}

function resumeVoiceRecognition() {
  if (!isListening) {
    // If voice was off entirely, just turn it on instead of refusing.
    // Better UX than telling a presenter "voice control is not active".
    _voicePaused = false;
    try { localStorage.removeItem('codeup_voice_paused'); } catch (e) {}
    startListening();
    return;
  }
  if (!_voicePaused) { speak('Voice is already listening.'); return; }
  _voicePaused = false;
  try { localStorage.removeItem('codeup_voice_paused'); } catch (e) {}

  const btn = document.getElementById('voiceButton');
  if (btn) {
    btn.textContent = '🎤 Voice (ON)';
    btn.setAttribute('aria-pressed', 'true');
    btn.classList.remove('cu-button-voice--paused');
    btn.classList.add('cu-button-voice--active');
  }

  // Force a fresh recognition session. If the session silently died during
  // pause (common after >30s of silence), this brings it back. If the session
  // is still alive, stop() just triggers a clean restart via onend.
  try {
    recognition.stop();
    // onend will fire and auto-restart within 400ms. Reset activity timer
    // so the watchdog doesn't immediately kick again.
    _lastRecognitionActivity = Date.now();
  } catch (e) {
    _debugLog('Resume: stop failed, trying direct restart', e.message);
    try { recognition.start(); _lastRecognitionActivity = Date.now(); }
    catch (e2) { _debugLog('Resume: direct restart also failed', e2.message); }
  }

  // Ascending tones — mirror of the pause cue
  SonificationManager.playTone(500, 0.08, 0.1);
  setTimeout(() => SonificationManager.playTone(700, 0.12, 0.1), 100);

  const lang = getLanguage();
  if (lang === 'hi') {
    speak('Voice फिर से चालू है।');
  } else {
    speak('Voice is back on.');
  }
  srAnnounce('Voice resumed');
  _debugLog('Voice: Resumed');
}

// ---------- VOICE COMMAND HANDLER ----------
async function handleVoiceCommand(rawText) {
  // FAST PATH: if a walkthrough is running, intercept "stop" / "shut up" /
  // "be quiet" / "cancel" client-side BEFORE the /voice-command round trip.
  // Going through the backend takes ~200ms and by then the walkthrough has
  // already moved on to the next line, defeating the whole point of "stop".
  // Exact match only — substring match would kill the walkthrough whenever
  // a longer command happens to contain one of these words (e.g. "stop the
  // explanation" or any Hindi phrase containing "रुक").
  if (_walkActive) {
    const t = rawText.toLowerCase().trim();
    const stopWords = ['stop', 'stop it', 'shut up', 'be quiet', 'silence',
                       'stop talking', 'cancel', 'enough', 'quit',
                       'रुको', 'बंद करो', 'चुप', 'रुक'];
    if (stopWords.some(w => t === w)) {
      _walkActive = false;
      SpeechManager.cancelAll();
      SonificationManager.clearAll();
      ErrorBeaconManager.stop();
      out('Stopped.');
      SonificationManager.playTone(400, 0.08, 0.08);
      srAnnounce('Stopped');
      return;
    }
  }

  const _ts = tabState();
  // Quiz answer intercept — per-tab state
  if (_ts._pendingQuizAnswer) {
    if (_ts._pendingQuizAnswer.expiresAt && Date.now() > _ts._pendingQuizAnswer.expiresAt) {
      _ts._pendingQuizAnswer = null;
    }
  }
  if (_ts._pendingQuizAnswer) {
    const t = rawText.toLowerCase().trim();
    const match = t.match(/(?:answer|option|choose)\s+([abcd])|^([abcd])$/);
    if (match) {
      const q = _ts._pendingQuizAnswer;
      _ts._pendingQuizAnswer = null;
      const chosen = (match[1] || match[2]).toUpperCase();
      if (chosen === q.answer) {
        SonificationManager.playTone(900, 0.1, 0.1);
        speak(`Correct! ${q.explanation}`);
        srAnnounce('Correct answer');
        out(`✓ CORRECT!\n\n${q.explanation}`);
      } else {
        SonificationManager.playTone(200, 0.15, 0.08);
        speak(`Not quite. The correct answer was ${q.answer}. ${q.explanation}`);
        srAnnounce('Wrong answer');
        out(`✗ The correct answer was ${q.answer}.\n\n${q.explanation}`);
      }
      return;
    }
  }

  // Bug challenge reveal intercept — per-tab state
  if (_ts._pendingBugChallenge) {
    if (_ts._pendingBugChallenge.expiresAt && Date.now() > _ts._pendingBugChallenge.expiresAt) {
      _ts._pendingBugChallenge = null;
    }
  }
  if (_ts._pendingBugChallenge) {
    const t = rawText.toLowerCase().trim();
    if (t.includes('show answer') || t.includes('give up') || t.includes('reveal') || t.includes('answer दिखाओ')) {
      const ch = _ts._pendingBugChallenge;
      _ts._pendingBugChallenge = null;
      out(`THE BUG:\n${ch.bug}\n\nFIXED CODE:\n${ch.fixed}`);
      speak(`The bug was: ${ch.bug}`);
      setTimeout(() => setCode(ch.fixed), 2000);
      srAnnounce('Answer revealed');
      return;
    }
  }

  if (pendingConfirm) {
    const handled = tryResolveConfirmation(rawText);
    if (handled) return;
    // Confirm was abandoned. The user said something that wasn't a yes/no
    // to our question — treat it as a fresh command and fall through.
  }

  const cleaned = rawText.toLowerCase().trim()
    .replace(/^(please|can you|could you|would you|hey|okay|ok)\s+/gi, '')
    .replace(/\s+(please|thanks|thank you)$/gi, '')
    .trim();

  _debugLog('Voice parsing:', cleaned);

  try {
    const res  = await fetch('/voice-command', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ text: cleaned }),
    });
    const data = await res.json();

    // Handle confirm intent before the general success branch so it isn't
    // swallowed by handleConfirmedAction (which has no 'confirm' case)
    if (data.action === 'confirm') {
      const opts = data.options || [];
      pendingConfirm = {
        options:   opts,
        expiresAt: Date.now() + 15000,
        context:   { heard: data.heard || rawText, raw: rawText },
      };
      const optsSpoken = opts.map(o => o.replace(/_/g, ' ')).join(' or ');
      const heard = data.heard || rawText;
      speak(`Did you mean ${optsSpoken}? Say first or second, or just say a new command.`);
      out(`Heard: "${heard}"\nDid you mean: ${optsSpoken}?\nSay "first" / "second", a new command, or "cancel".`);
      return;
    }

    if (data.success && data.action && data.action !== 'unknown') {
      _debugLog('Backend action:', data.action);
      await handleConfirmedAction(data.action, data);
    } else {
      speak("I didn't understand that command. Say 'help' for available commands.");
      _debugLog('Command not recognized:', cleaned);
    }
  } catch (e) {
    console.error('Backend interpretation failed:', e);
    speak("Command not recognized. Say 'help' for available commands.");
  }
}

// ---------- KEYBOARD SHORTCUTS ----------
window.addEventListener('DOMContentLoaded', () => {
  const resumeAudio = () => {
    if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume().catch(() => {});
  };
  document.addEventListener('click', resumeAudio);

  document.addEventListener('keydown', e => {
    resumeAudio();
    if (e.ctrlKey && e.shiftKey && e.key === 'M') { e.preventDefault(); toggleVoice(); }
    // Escape stops speech immediately. Ignored when command palette or input
    // dialog is open — those have their own Escape handlers.
    if (e.key === 'Escape') {
      const paletteOverlay = document.getElementById('commandPaletteOverlay');
      const paletteOpen = paletteOverlay && !paletteOverlay.hasAttribute('hidden');
      const dialogOpen  = !!document.getElementById('_cuInputDialog');
      if (paletteOpen || dialogOpen) return;
      if (AppState.isSpeaking || (window.speechSynthesis && window.speechSynthesis.speaking) || _walkActive) {
        _walkActive = false;
        SpeechManager.cancelAll();
        ErrorBeaconManager.stop();
        srAnnounce('Speech stopped');
        SonificationManager.playTone(600, 0.05, 0.06);
        e.preventDefault();
      }
    }
  });

  // Command palette input — registered once here only (removed the duplicate at bottom of file)
  const paletteInput = document.getElementById('commandPaletteInput');
  if (paletteInput) {
    paletteInput.addEventListener('input', e => {
      commandPaletteSelectedIndex = 0;
      renderCommandPalette(e.target.value);
    });
    // Escape must be caught on the INPUT itself so Monaco never sees it
    paletteInput.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeCommandPalette(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); commandPaletteSelectedIndex++; renderCommandPalette(paletteInput.value); }
      else if (e.key === 'ArrowUp')   { e.preventDefault(); commandPaletteSelectedIndex--; renderCommandPalette(paletteInput.value); }
      else if (e.key === 'Enter')     { e.preventDefault(); executeCommandPaletteItem(commandPaletteSelectedIndex); }
    });
  }

  // Ctrl+Shift+P opens the palette — document-level is fine for this one
  document.addEventListener('keydown', e => {
    if (e.ctrlKey && e.shiftKey && e.key === 'P') { e.preventDefault(); openCommandPalette(); }
  });

  // Click outside the container closes the palette
  const paletteOverlay = document.getElementById('commandPaletteOverlay');
  if (paletteOverlay) {
    paletteOverlay.addEventListener('click', e => {
      if (e.target === paletteOverlay) closeCommandPalette();
    });
  }
});

function registerEditorShortcuts() {
  if (window._editorShortcutsRegistered) return;
  if (!editor) return;
  window._editorShortcutsRegistered = true;

  // Ctrl+Enter: run code. Registered as a Monaco editor command only —
  // Monaco swallows the event before the document-level handler sees it,
  // which is fine because this is the only path we need.
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => { runCode(); });

  // Escape inside Monaco — stop speech immediately. Monaco normally swallows
  // Escape (its suggestion widget and command palette consume it first), so
  // we also listen on the editor's DOM node in capture phase to beat them.
  editor.addCommand(monaco.KeyCode.Escape, () => {
    if (AppState.isSpeaking || (window.speechSynthesis && window.speechSynthesis.speaking)) {
      SpeechManager.cancelAll();
      ErrorBeaconManager.stop();
      srAnnounce('Speech stopped');
      SonificationManager.playTone(600, 0.05, 0.06);
    }
  });
  // Capture-phase listener on the editor's DOM container. Fires BEFORE
  // Monaco's suggestion widget / IntelliSense popup can swallow Escape,
  // so speech still stops even when those popups are open. We don't
  // preventDefault — the popup can still close after we cancel speech.
  const editorDom = editor.getDomNode();
  if (editorDom) {
    editorDom.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' &&
          (AppState.isSpeaking || (window.speechSynthesis && window.speechSynthesis.speaking))) {
        SpeechManager.cancelAll();
        ErrorBeaconManager.stop();
        srAnnounce('Speech stopped');
        SonificationManager.playTone(600, 0.05, 0.06);
      }
    }, true);  // capture phase — beats Monaco's internal handlers
  }

  // All Alt-shortcut entry points cancel pending speech first so a new
  // user action immediately interrupts whatever's currently being said.
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyS, () => { SpeechManager.cancelAll(); sonifyCurrentBlock(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyL, () => { SpeechManager.cancelAll(); const pos = editor.getPosition() || { lineNumber: 1 }; readLineEnhanced(pos.lineNumber); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyV, () => { SpeechManager.cancelAll(); listVariables(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyE, () => { SpeechManager.cancelAll(); checkSyntaxErrors(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyN, () => { SpeechManager.cancelAll(); speakNextStep(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyH, () => { SpeechManager.cancelAll(); showHelp(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyB, () => { SpeechManager.cancelAll(); readBreadcrumb(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.KeyW, () => { walkThroughCode(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.LeftArrow,  () => { navigateBack(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.RightArrow, () => { navigateForward(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.Home, () => { goToTop(); });
  editor.addCommand(monaco.KeyMod.Alt | monaco.KeyCode.End,  () => { goToBottom(); });
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyC, () => { copyCode(); });
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyV, () => { pasteCode(); });

  try { loadSnippets(); } catch (e) {}
  try { startAutosave(); } catch (e) { console.warn('autosave init failed', e); }
  try { recoverAutosaveDraft(); } catch (e) { console.warn('autosave recover failed', e); }
  updateInputModeUI();
  updateInputsPanel();
  _debugLog('All accessibility features loaded.');
}

// ---------- AUTOSAVE ----------
// Periodically writes the editor contents to localStorage so a refresh
// or accidental tab-close doesn't lose work. Recovery prompts on next load.
function startAutosave() {
  if (_autosaveTimer) return;
  _autosaveTimer = setInterval(() => {
    try {
      const code = getCode();
      if (code === _autosaveLastCode) return;  // no-op if nothing changed
      if (!code.trim()) return;                 // don't autosave empty
      localStorage.setItem(AUTOSAVE_KEY, JSON.stringify({
        code,
        timestamp: Date.now(),
      }));
      _autosaveLastCode = code;
    } catch (e) { /* localStorage full or disabled — silent fail */ }
  }, AUTOSAVE_INTERVAL_MS);
}

function recoverAutosaveDraft() {
  try {
    const raw = localStorage.getItem(AUTOSAVE_KEY);
    if (!raw) return;
    const draft = JSON.parse(raw);
    if (!draft || !draft.code) return;
    // Only restore if the editor is empty/default — don't clobber an active session
    const current = getCode().trim();
    const isDefault = !current || current === 'print("Hello CodeUp!")';
    if (!isDefault) return;
    // Only restore drafts from within the last 7 days — older is probably stale
    const ageMs = Date.now() - (draft.timestamp || 0);
    if (ageMs > 7 * 24 * 60 * 60 * 1000) {
      localStorage.removeItem(AUTOSAVE_KEY);
      return;
    }
    setCode(draft.code);
    speak('A draft from your previous session has been restored. Press Control Z to undo if you did not want this.');
    srAnnounce('Previous draft restored');
  } catch (e) { /* corrupted or missing — silent fail */ }
}

async function speakNextStep() {
  await handleCommandText('next step');
}

// ---------- STRUCTURE PANEL ----------
let lastStructureData = null;

async function updateStructurePanel() {
  if (!editor) return;
  const code    = editor.getValue();
  const panel   = document.getElementById('structurePanel');
  const content = document.getElementById('structureContent');
  if (!code.trim()) { hideEl(panel); return; }

  try {
    const res  = await fetch('/structure', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code }),
    });
    const data = await res.json();

    if (!data.success || !data.structure) {
      content.innerHTML = '<p class="structure-info">Unable to parse structure.</p>';
      showEl(panel);
      return;
    }

    lastStructureData = data.structure;
    const { imports, functions, classes, loops } = data.structure;
    let html = '';

    if (imports.length > 0) {
      html += '<div class="structure-group"><div class="structure-group-title">📦 Imports</div>';
      imports.forEach(imp => {
        html += `<div class="structure-item" role="button" tabindex="0" data-line="1">
          <span class="structure-item-icon">📦</span>
          <span class="structure-item-label">${escapeHtml(imp)}</span>
        </div>`;
      });
      html += '</div>';
    }

    if (classes.length > 0) {
      html += '<div class="structure-group"><div class="structure-group-title">🏛️ Classes</div>';
      classes.forEach(cls => {
        html += `<div class="structure-item" role="button" tabindex="0" data-line="${cls.line}" aria-label="Go to class ${escapeHtml(cls.name)} at line ${cls.line}">
          <span class="structure-item-icon">🏛️</span>
          <span class="structure-item-label">${escapeHtml(cls.name)}</span>
          <span class="structure-item-line">L${cls.line}</span>
        </div>`;
      });
      html += '</div>';
    }

    if (functions.length > 0) {
      html += '<div class="structure-group"><div class="structure-group-title">⚙️ Functions</div>';
      functions.forEach(fn => {
        const params = fn.params.map(p => p.name).join(', ');
        const asyncBadge = fn.is_async ? '<span style="color:#facc15;font-size:0.7rem;margin-right:4px;">async</span>' : '';
        const parentLabel = fn.parent_class ? `<span style="color:#64748b;font-size:0.75rem;">${escapeHtml(fn.parent_class)}.</span>` : '';
        const icon = fn.is_async ? '⚡' : '⚙️';
        const ariaLabel = `Go to ${fn.is_async ? 'async ' : ''}function ${fn.parent_class ? fn.parent_class + '.' : ''}${fn.name} at line ${fn.line}`;
        html += `<div class="structure-item" role="button" tabindex="0" data-line="${fn.line}" aria-label="${escapeHtml(ariaLabel)}">
          <span class="structure-item-icon">${icon}</span>
          <span class="structure-item-label">${asyncBadge}${parentLabel}${escapeHtml(fn.name)}(${escapeHtml(params)})</span>
          <span class="structure-item-line">L${fn.line}</span>
        </div>`;
      });
      html += '</div>';
    }

    if (loops.length > 0) {
      html += '<div class="structure-group"><div class="structure-group-title">🔄 Loops</div>';
      loops.forEach((loop, idx) => {
        html += `<div class="structure-item" role="button" tabindex="0" data-line="${loop.line}" aria-label="Go to loop at line ${loop.line}">
          <span class="structure-item-icon">🔄</span>
          <span class="structure-item-label">Loop #${idx + 1}</span>
          <span class="structure-item-line">L${loop.line}</span>
        </div>`;
      });
      html += '</div>';
    }

    if (!imports.length && !functions.length && !classes.length && !loops.length) {
      html = '<p class="structure-info">No structures found.</p>';
    }

    content.innerHTML = html;
    showEl(panel);

    // Use event delegation — line numbers come from data attributes, not inline JS strings
    content.querySelectorAll('.structure-item').forEach(item => {
      const go = () => {
        const line = parseInt(item.dataset.line, 10);
        if (!isNaN(line)) gotoLine(line);
      };
      item.addEventListener('click',   go);
      item.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    });

  } catch (e) {
    console.error('Structure parse error:', e);
    content.innerHTML = '<p class="structure-info">Error parsing structure.</p>';
    showEl(panel);
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ---------- AUTOCOMPLETE ----------
const PYTHON_KEYWORDS = [
  'False','None','True','and','as','assert','async','await','break','class',
  'continue','def','del','elif','else','except','finally','for','from','global',
  'if','import','in','is','lambda','nonlocal','not','or','pass','raise','return',
  'try','while','with','yield',
];

const PYTHON_BUILTINS = [
  'abs','all','any','ascii','bin','bool','bytearray','bytes','callable','chr',
  'classmethod','compile','complex','delattr','dict','dir','divmod','enumerate',
  'eval','exec','filter','float','format','frozenset','getattr','globals','hasattr',
  'hash','help','hex','id','input','int','isinstance','issubclass','iter','len',
  'list','locals','map','max','memoryview','min','next','object','oct','open','ord',
  'pow','print','property','range','repr','reversed','round','set','setattr','slice',
  'sorted','staticmethod','str','sum','super','tuple','type','vars','zip',
];

const PYTHON_SNIPPETS = {
  'if':       { label: 'if statement',         insertText: 'if ${1:condition}:\n\t${0:pass}',                                                                    kind: 'Snippet' },
  'for':      { label: 'for loop',             insertText: 'for ${1:item} in ${2:items}:\n\t${0:pass}',                                                           kind: 'Snippet' },
  'while':    { label: 'while loop',           insertText: 'while ${1:condition}:\n\t${0:pass}',                                                                  kind: 'Snippet' },
  'def':      { label: 'function',             insertText: 'def ${1:function_name}(${2:args}):\n\t"""${3:docstring}"""\n\t${0:pass}',                              kind: 'Snippet' },
  'class':    { label: 'class',                insertText: 'class ${1:ClassName}:\n\t"""${2:docstring}"""\n\tdef __init__(self):\n\t\t${0:pass}',                  kind: 'Snippet' },
  'try':      { label: 'try-except',           insertText: 'try:\n\t${1:pass}\nexcept ${2:Exception} as ${3:e}:\n\t${0:pass}',                                    kind: 'Snippet' },
  'with':     { label: 'with statement',       insertText: 'with ${1:context} as ${2:var}:\n\t${0:pass}',                                                         kind: 'Snippet' },
  'lambda':   { label: 'lambda function',      insertText: 'lambda ${1:x}: ${0:x}',                                                                              kind: 'Snippet' },
  'list-comp':{ label: 'list comprehension',   insertText: '[${1:x} for ${2:x} in ${3:items}]',                                                                  kind: 'Snippet' },
  'dict-comp':{ label: 'dict comprehension',   insertText: '{${1:k}: ${2:v} for ${3:k}, ${4:v} in ${5:items}}',                                                  kind: 'Snippet' },
  '__main__': { label: 'main block',           insertText: 'if __name__ == "__main__":\n\t${0:main()}',                                                           kind: 'Snippet' },
};

function registerPythonAutocomplete() {
  if (!monaco || !monaco.languages) return;
  monaco.languages.registerCompletionItemProvider('python', {
    provideCompletionItems(model, position) {
      const word  = model.getWordUntilPosition(position);
      const range = { startLineNumber: position.lineNumber, endLineNumber: position.lineNumber, startColumn: word.startColumn, endColumn: word.endColumn };
      const suggestions = [];

      PYTHON_KEYWORDS.forEach(kw => suggestions.push({ label: kw, kind: monaco.languages.CompletionItemKind.Keyword, insertText: kw, range }));
      PYTHON_BUILTINS.forEach(fn => suggestions.push({ label: fn + '()', kind: monaco.languages.CompletionItemKind.Function, insertText: fn + '($0)', range, sortText: '1_' + fn }));
      Object.entries(PYTHON_SNIPPETS).forEach(([key, sn]) => suggestions.push({
        label: sn.label, kind: monaco.languages.CompletionItemKind.Snippet,
        insertText: sn.insertText, insertTextRules: monaco.languages.CompletionItemInsertTextRule.InsertAsSnippet,
        range, sortText: '2_' + key,
      }));

      const codeText = model.getValue();
      const variables = [...new Set((codeText.match(/^[a-zA-Z_]\w*/gm) || []))];
      variables.forEach(v => {
        if (!PYTHON_KEYWORDS.includes(v) && !PYTHON_BUILTINS.includes(v)) {
          suggestions.push({ label: v, kind: monaco.languages.CompletionItemKind.Variable, insertText: v, range, sortText: '3_' + v });
        }
      });

      return { suggestions };
    },
    triggerCharacters: [],
  });
}

// ---------- FUNCTION / CLASS SONIFICATION ----------
async function sonifyFunction(functionName) {
  if (!functionName) { speak('Please specify a function name.'); return; }
  const lines = getCode().split('\n');
  // Escape regex metacharacters in the function name before building the pattern
  const pattern = new RegExp(`^\\s*def\\s+${escapeRegex(functionName)}\\s*\\(`, 'i');

  let startLine = -1, endLine = -1;
  for (let i = 0; i < lines.length; i++) {
    if (pattern.test(lines[i])) {
      startLine = i + 1;
      const baseIndent = lines[i].search(/\S/);
      for (let j = i + 1; j < lines.length; j++) {
        if (lines[j].trim() === '') continue;
        if (lines[j].search(/\S/) <= baseIndent) { endLine = j; break; }
      }
      if (endLine === -1) endLine = lines.length;
      break;
    }
  }

  if (startLine === -1) { speak(`Function ${functionName} not found.`); return; }
  speak(`Sonifying function ${functionName} from line ${startLine} to ${endLine}.`);
  await sonifyRange(startLine, endLine, 'function');
}

async function sonifyClass(className) {
  if (!className) { speak('Please specify a class name.'); return; }
  const lines   = getCode().split('\n');
  const pattern = new RegExp(`^\\s*class\\s+${escapeRegex(className)}\\s*[:\\(]`, 'i');

  let startLine = -1, endLine = -1;
  for (let i = 0; i < lines.length; i++) {
    if (pattern.test(lines[i])) {
      startLine = i + 1;
      const baseIndent = lines[i].search(/\S/);
      for (let j = i + 1; j < lines.length; j++) {
        if (lines[j].trim() === '') continue;
        if (lines[j].search(/\S/) <= baseIndent) { endLine = j; break; }
      }
      if (endLine === -1) endLine = lines.length;
      break;
    }
  }

  if (startLine === -1) { speak(`Class ${className} not found.`); return; }
  speak(`Sonifying class ${className} from line ${startLine} to ${endLine}.`);
  await sonifyRange(startLine, endLine, 'class');
}

async function sonifyRange(startLine, endLine, context = 'block') {
  const lines = getCode().split('\n');
  const contextFreqs = { function: 900, class: 1000, loop: 400, block: 600 };
  const baseFreq = contextFreqs[context] || 600;

  for (let i = startLine - 1; i < Math.min(endLine, lines.length); i++) {
    const indent = lines[i].search(/\S/);
    // Normalized volume consistent with all other sonification (0.08 not 0.3)
    SonificationManager.playTone(baseFreq + 50 * Math.min(indent / 2, 5), 0.05, 0.08);
    await sleep(100);
  }
  speak(`Finished sonifying ${context}.`);
}

// ---------- ERROR SONIFICATION ----------
const ERROR_SONIFICATION_MAP = {
  SyntaxError:       { freq: 200, duration: 300, label: 'syntax error' },
  IndentationError:  { freq: 250, duration: 250, label: 'indentation error' },
  NameError:         { freq: 400, duration: 200, label: 'name error' },
  TypeError:         { freq: 500, duration: 200, label: 'type error' },
  ValueError:        { freq: 550, duration: 200, label: 'value error' },
  AttributeError:    { freq: 600, duration: 150, label: 'attribute error' },
  KeyError:          { freq: 650, duration: 150, label: 'key error' },
  IndexError:        { freq: 700, duration: 150, label: 'index error' },
  ImportError:       { freq: 800, duration: 150, label: 'import error' },
  RuntimeError:      { freq: 900, duration: 150, label: 'runtime error' },
  ZeroDivisionError: { freq: 950, duration: 150, label: 'division by zero' },
  Warning:           { freq: 1100, duration: 100, label: 'warning' },
  Style:             { freq: 1200, duration: 80,  label: 'style issue' },
};

function classifyError(errorMessage) {
  const lower = errorMessage.toLowerCase();
  for (const [type] of Object.entries(ERROR_SONIFICATION_MAP)) {
    if (lower.includes(type.toLowerCase())) return type;
  }
  if (lower.includes('unexpected') || lower.includes('invalid')) return 'SyntaxError';
  if (lower.includes('not defined') || lower.includes('undefined')) return 'NameError';
  if (lower.includes('warning')) return 'Warning';
  return 'RuntimeError';
}

function sonifyError(errorMessage, errorLine = null) {
  const config = ERROR_SONIFICATION_MAP[classifyError(errorMessage)] || ERROR_SONIFICATION_MAP.RuntimeError;
  SonificationManager.playTone(config.freq, config.duration, 0.4);
  speak(`${config.label} on line ${errorLine || 'unknown'}. ${errorMessage.substring(0, 50)}`);
}

async function sonifyCodeIssues() {
  const lines  = getCode().split('\n');
  const issues = [];

  lines.forEach((line, idx) => {
    const indent = line.search(/\S/);
    // Inconsistent indentation check
    if (indent !== -1 && indent % 4 !== 0 && indent % 2 !== 0) {
      issues.push({ line: idx + 1, type: 'Style', message: 'Inconsistent indentation' });
    }
    // Detect bare assignment (=) inside if/while condition — heuristic
    const trimmed = line.trim();
    if (/^(if|elif|while)\s+/.test(trimmed) && /[^=!<>]=(?!=)/.test(trimmed)) {
      issues.push({ line: idx + 1, type: 'Warning', message: 'Possible assignment in condition' });
    }
  });

  if (issues.length === 0) { speak('No code issues detected.'); return; }
  speak(`Found ${issues.length} issue${issues.length !== 1 ? 's' : ''}.`);
  for (const issue of issues) { sonifyError(issue.message, issue.line); await sleep(300); }
}

// ---------- DEBUG SUGGESTIONS ----------
async function getDebugSuggestions() {
  const code = getCode();
  if (!code.trim()) { speak('Code is empty.'); return; }
  speak('Analyzing code for improvement suggestions...');
  try {
    const res  = await fetch('/debug-suggestions', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code, language: getLanguage() }),
    });
    const data = await res.json();
    if (!data.success || !data.suggestions) { out('No suggestions available.'); speak('Could not generate suggestions.'); return; }
    if (data.suggestions.length === 0) { out('Code looks good! No issues found.'); speak('Code looks good. No issues found.'); return; }

    let output = 'DEBUG SUGGESTIONS:\n\n';
    let speech = `Found ${data.suggestions.length} suggestion${data.suggestions.length !== 1 ? 's' : ''}. `;
    data.suggestions.forEach((sugg, idx) => { output += `${sugg.icon} ${sugg.text}\n\n`; speech += `Item ${idx + 1}: ${sugg.text}. `; });
    out(output); speak(speech);
    // Glyph decorations require a line number from the backend — skipping until backend provides it
  } catch (e) {
    console.error('Debug suggestions error:', e); speak('Error getting suggestions.');
  }
}

// ---------- COMMAND PALETTE ----------
const COMMAND_PALETTE_COMMANDS = [
  { id: 'run',              title: 'Run Code',           desc: 'Execute Python code',                icon: '▶',  keys: 'Ctrl+Enter',   action: () => runCode() },
  { id: 'analyze',          title: 'Analyze Code',        desc: 'AI analysis of code',               icon: '🔍', keys: 'Ctrl+Alt+A',   action: () => analyzeCode() },
  { id: 'fix',              title: 'Fix Code',            desc: 'Automatically fix errors',          icon: '🔧', keys: 'Ctrl+Alt+F',   action: () => fixCode() },
  { id: 'advise',           title: 'Get Advice',          desc: 'Suggestions for improvements',      icon: '💡', keys: 'Ctrl+Alt+I',   action: () => adviseCode() },
  { id: 'goto_line',        title: 'Go to Line',          desc: 'Jump to specific line',             icon: '➡️', keys: 'Ctrl+G',       action: () => showInputDialog('Enter line number:', gotoLine) },
  { id: 'read_line',        title: 'Read Line',           desc: 'Read current line with context',    icon: '📖', keys: '',             action: () => readCurrentLine() },
  { id: 'next_line',        title: 'Next Line',           desc: 'Move to next line',                 icon: '↓',  keys: 'Down',         action: () => nextLine() },
  { id: 'prev_line',        title: 'Previous Line',       desc: 'Move to previous line',             icon: '↑',  keys: 'Up',           action: () => prevLine() },
  { id: 'show_structure',   title: 'Show Structure',      desc: 'Display code navigation map',       icon: '🗺️', keys: 'Ctrl+Shift+S', action: () => toggleStructurePanel() },
  { id: 'sonify_block',     title: 'Sonify Block',        desc: 'Hear current code block',           icon: '🔊', keys: 'Alt+S',        action: () => sonifyCurrentBlock() },
  { id: 'next_step',        title: 'Next step',           desc: 'Step forward in execution trace',   icon: '⏭',  keys: 'Alt+N',        action: () => speakNextStep() },
  { id: 'prev_step',        title: 'Previous step',       desc: 'Step back in execution trace',      icon: '⏮',  keys: '',             action: () => handleCommandText('previous step') },
  { id: 'save_snippet',     title: 'Save Snippet',        desc: 'Save code as snippet',              icon: '💾', keys: 'Ctrl+S',       action: () => saveSnippet() },
  { id: 'list_variables',   title: 'List Variables',      desc: 'Show all variables in scope',       icon: '📊', keys: 'Ctrl+Alt+V',   action: () => listVariables() },
  { id: 'check_errors',     title: 'Check Errors',        desc: 'Find syntax errors',                icon: '⚠️', keys: '',             action: () => checkSyntaxErrors() },
  { id: 'locate_error',     title: 'Locate Error',        desc: 'Jump to first error',               icon: '🎯', keys: 'Ctrl+Alt+E',   action: () => locateError() },
  { id: 'clear_editor',     title: 'Clear Editor',        desc: 'Delete all code',                   icon: '🗑️', keys: '',             action: () => clearEditor() },
  { id: 'copy_code',        title: 'Copy Code',           desc: 'Copy to clipboard',                 icon: '📋', keys: 'Ctrl+C',       action: () => copyCode() },
  { id: 'paste_code',       title: 'Paste Code',          desc: 'Paste from clipboard',              icon: '📌', keys: 'Ctrl+V',       action: () => pasteCode() },
  { id: 'debug_suggestions',title: 'Debug Suggestions',   desc: 'Get AI debugging hints',            icon: '🔬', keys: '',             action: () => getDebugSuggestions() },
  { id: 'sonify_issues',    title: 'Sonify Issues',       desc: 'Hear code problems',                icon: '🔊', keys: '',             action: () => sonifyCodeIssues() },
  { id: 'help',             title: 'Show Help',           desc: 'Display all commands',              icon: '❓', keys: 'F1',           action: () => showHelp() },
];

let commandPaletteSelectedIndex = 0;

function openCommandPalette() {
  const overlay = document.getElementById('commandPaletteOverlay');
  const input   = document.getElementById('commandPaletteInput');
  showEl(overlay);
  commandPaletteSelectedIndex = 0;
  renderCommandPalette('');
  // Focus after a tick so Monaco doesn't reclaim focus immediately
  requestAnimationFrame(() => { if (input) { input.focus(); speak('Command palette open. Type to search, arrow keys to navigate, Enter to select, Escape to close.'); } });
}

function closeCommandPalette() {
  hideEl(document.getElementById('commandPaletteOverlay'));
  // Return focus to editor so keyboard users aren't stranded
  if (editor) editor.focus();
  speak('Command palette closed.');
}


function renderCommandPalette(filterText) {
  const resultsContainer = document.getElementById('commandPaletteResults');
  if (!resultsContainer) return;

  const query    = filterText.toLowerCase().trim();
  let   filtered = COMMAND_PALETTE_COMMANDS;
  if (query) {
    filtered = COMMAND_PALETTE_COMMANDS.filter(cmd =>
      cmd.title.toLowerCase().includes(query) ||
      cmd.desc.toLowerCase().includes(query)  ||
      cmd.id.toLowerCase().includes(query)
    );
  }

  if (filtered.length === 0) { resultsContainer.innerHTML = '<div class="command-palette-empty">No commands found</div>'; commandPaletteSelectedIndex = -1; return; }
  commandPaletteSelectedIndex = Math.max(0, Math.min(commandPaletteSelectedIndex, filtered.length - 1));

  resultsContainer.innerHTML = filtered.map((cmd, idx) => `
    <div class="command-palette-item ${idx === commandPaletteSelectedIndex ? 'selected' : ''}"
         role="option" aria-selected="${idx === commandPaletteSelectedIndex}" data-index="${idx}">
      <span class="command-palette-item-icon">${cmd.icon}</span>
      <div class="command-palette-item-main">
        <div class="command-palette-item-title">${escapeHtml(cmd.title)}</div>
        <div class="command-palette-item-desc">${escapeHtml(cmd.desc)}</div>
      </div>
      ${cmd.keys ? `<div class="command-palette-item-shortcut">${escapeHtml(cmd.keys)}</div>` : ''}
    </div>
  `).join('');

  resultsContainer.querySelectorAll('.command-palette-item').forEach((item, idx) => {
    item.addEventListener('click', () => executeCommandPaletteItem(idx));
  });
}

function executeCommandPaletteItem(index) {
  const input    = document.getElementById('commandPaletteInput');
  const query    = input ? input.value.toLowerCase().trim() : '';
  let   filtered = COMMAND_PALETTE_COMMANDS;
  if (query) filtered = COMMAND_PALETTE_COMMANDS.filter(cmd => cmd.title.toLowerCase().includes(query) || cmd.desc.toLowerCase().includes(query) || cmd.id.toLowerCase().includes(query));
  if (index < 0 || index >= filtered.length) return;
  closeCommandPalette();
  try { filtered[index].action(); } catch (e) { console.error('Command error:', e); speak('Error executing command.'); }
}

function toggleStructurePanel() {
  const panel = document.getElementById('structurePanel');
  if (!panel) return;
  // Use hidden attribute consistently (not style.display)
  if (panel.hasAttribute('hidden')) {
    showEl(panel);
    speak('Structure panel shown.');
  } else {
    hideEl(panel);
    speak('Structure panel hidden.');
  }
}

// ---------- VOICE CODE EDITING ----------

function insertAtCursor(text) {
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const pos = editor.getPosition() || { lineNumber: model.getLineCount(), column: 1 };
  const line = pos.lineNumber;
  const col  = model.getLineMaxColumn(line);
  model.pushEditOperations([], [{
    range: new monaco.Range(line, col, line, col),
    text:  '\n' + text,
  }], () => null);
  const newLine = line + text.split('\n').length;
  editor.setPosition({ lineNumber: newLine, column: 1 });
  editor.revealLineInCenter(newLine);
}

function insertFunctionVoice(functionName) {
  const name = functionName || 'my_function';
  const code = `def ${name}():\n    pass`;
  insertAtCursor(code);
  speak(`Inserted function ${name}. Cursor is on the pass line. Add your code there.`);
  srAnnounce(`Function ${name} inserted`);
}

function insertClassVoice(className) {
  const name = className || 'MyClass';
  const code = `class ${name}:\n    def __init__(self):\n        pass`;
  insertAtCursor(code);
  speak(`Inserted class ${name} with an init method.`);
  srAnnounce(`Class ${name} inserted`);
}

function insertLoopVoice(loopVar, iterable) {
  const v = loopVar  || 'i';
  const it = iterable || 'range(10)';
  const code = `for ${v} in ${it}:\n    pass`;
  insertAtCursor(code);
  speak(`Inserted for loop. Variable ${v} in ${it}. Replace pass with your loop body.`);
  srAnnounce('For loop inserted');
}

function insertIfVoice(condition) {
  const cond = condition || 'True';
  const code = `if ${cond}:\n    pass`;
  insertAtCursor(code);
  speak(`Inserted if statement checking ${cond}. Replace pass with your code.`);
  srAnnounce('If statement inserted');
}

function appendLineVoice(text) {
  if (!text) { speak('No text to append.'); return; }
  insertAtCursor(text);
  speak(`Appended: ${text}`);
  srAnnounce('Line appended');
}

function replaceLineVoice(lineNum, text) {
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const maxLine = model.getLineCount();
  if (lineNum < 1 || lineNum > maxLine) { speak(`Line ${lineNum} is out of range.`); return; }
  const col = model.getLineMaxColumn(lineNum);
  model.pushEditOperations([], [{
    range: new monaco.Range(lineNum, 1, lineNum, col),
    text:  text,
  }], () => null);
  editor.setPosition({ lineNumber: lineNum, column: 1 });
  speak(`Replaced line ${lineNum} with: ${text}`);
  srAnnounce(`Line ${lineNum} replaced`);
}

function insertLineVoice(lineNum, text) {
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const maxLine = model.getLineCount();
  if (lineNum < 1 || lineNum > maxLine + 1) { speak(`Line ${lineNum} is out of range.`); return; }
  model.pushEditOperations([], [{
    range: new monaco.Range(lineNum, 1, lineNum, 1),
    text:  text + '\n',
  }], () => null);
  editor.setPosition({ lineNumber: lineNum, column: 1 });
  speak(`Inserted at line ${lineNum}: ${text}`);
  srAnnounce(`Line inserted at ${lineNum}`);
}

function addParameterVoice(paramName, functionName) {
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const code  = getCode();
  const lines = code.split('\n');

  // Find the target function
  let targetLine = -1;
  const pattern = functionName
    ? new RegExp(`^\\s*def\\s+${escapeRegex(functionName)}\\s*\\(`)
    : /^\s*def\s+\w+\s*\(/;

  for (let i = 0; i < lines.length; i++) {
    if (pattern.test(lines[i])) { targetLine = i + 1; break; }
  }

  if (targetLine === -1) {
    speak(functionName ? `Function ${functionName} not found.` : 'No function found to add parameter to.');
    return;
  }

  const lineContent = model.getLineContent(targetLine);
  const parenClose  = lineContent.lastIndexOf(')');
  if (parenClose === -1) { speak('Could not find function signature.'); return; }

  const parenOpen = lineContent.indexOf('(');
  const existing  = lineContent.slice(parenOpen + 1, parenClose).trim();
  const newParams = existing ? `${existing}, ${paramName}` : paramName;
  const newLine   = lineContent.slice(0, parenOpen + 1) + newParams + lineContent.slice(parenClose);

  model.pushEditOperations([], [{
    range: new monaco.Range(targetLine, 1, targetLine, model.getLineMaxColumn(targetLine)),
    text:  newLine,
  }], () => null);

  const fname = functionName || 'the function';
  speak(`Added parameter ${paramName} to ${fname}.`);
  srAnnounce(`Parameter ${paramName} added`);
}

// ---------- SEMANTIC AUTOCOMPLETE ----------

let _lastSuggestions = [];
let _suggestionsLang = 'en';

async function suggestNextLine() {
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const pos  = editor.getPosition() || { lineNumber: model.getLineCount() };
  showAI('Thinking of next lines...');
  speak('Analyzing context. Suggesting next lines.');

  try {
    const res  = await fetch('/suggest-next', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: getCode(), line: pos.lineNumber, language: getLanguage() }),
    });
    const data = await res.json();

    if (!data.success || !data.suggestions || data.suggestions.length === 0) {
      speak('Could not generate suggestions. Try writing a bit more code first.');
      hideAI(); return;
    }

    _lastSuggestions = data.suggestions;
    _suggestionsLang = getLanguage();

    const numbered = data.suggestions.map((s, i) => `${i + 1}: ${s}`).join('\n');
    out(`Suggested next lines:\n${numbered}\n\nSay "choose 1", "choose 2", or "choose 3" to insert.`);
    srAnnounce(`${data.suggestions.length} suggestions ready`);

    speak(`Here are ${data.suggestions.length} suggestions.`);
    data.suggestions.forEach((s, i) => speak(`Option ${i + 1}: ${s}`));
    speak('Say choose 1, choose 2, or choose 3 to insert your choice.');

  } catch (e) {
    console.error(e);
    speak('Suggestion failed. Please try again.');
  } finally {
    hideAI();
  }
}

function chooseSuggestion(choice) {
  if (!_lastSuggestions || _lastSuggestions.length === 0) {
    speak('No suggestions available. Say suggest next line first.');
    return;
  }

  let idx;
  if (typeof choice === 'number') {
    idx = choice - 1;
  } else {
    const words = { 'one': 0, 'two': 1, 'three': 2, 'first': 0, 'second': 1, 'third': 2 };
    idx = words[String(choice).toLowerCase()] !== undefined
      ? words[String(choice).toLowerCase()]
      : parseInt(choice, 10) - 1;
  }

  if (isNaN(idx) || idx < 0 || idx >= _lastSuggestions.length) {
    speak(`Invalid choice. Please say choose 1, 2, or 3.`);
    return;
  }

  const chosen = _lastSuggestions[idx];
  insertAtCursor(chosen);
  _lastSuggestions = [];
  speak(`Inserted: ${chosen}`);
  srAnnounce('Suggestion inserted');
}

// ---------- EXECUTION STORY MODE ----------

async function tellExecutionStory() {
  SpeechManager.cancelAll();
  showAI('Narrating your execution...');
  speak('Narrating what happened when your code ran.');
  try {
    const res  = await fetch('/execution-story', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ code: getCode(), language: getLanguage() }),
    });
    const data = await res.json();
    if (data.success) {
      out(data.story);
      speak(data.story);
      srAnnounce('Execution story ready');
    } else {
      out(data.story || 'No story available.');
      speak(data.story || 'Run your code first, then ask for the story.');
    }
  } catch (e) {
    console.error(e);
    speak('Could not narrate execution. Please try again.');
  } finally {
    hideAI();
  }
}

// ---------- AUDIO BREAKPOINT DEBUGGER ----------

let _breakpoints = new Set();
let _watchedVars = new Set();
let _breakpointDecorations = [];

function setBreakpoint(lineNum) {
  if (!lineNum) { speak('Please specify a line number for the breakpoint.'); return; }
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const maxLine = model.getLineCount();
  if (lineNum < 1 || lineNum > maxLine) { speak(`Line ${lineNum} is out of range.`); return; }

  _breakpoints.add(lineNum);

  // Visual decoration — red dot in gutter
  _breakpointDecorations = editor.deltaDecorations(_breakpointDecorations, [
    ...Array.from(_breakpoints).map(l => ({
      range: new monaco.Range(l, 1, l, 1),
      options: {
        isWholeLine: true,
        className:   'bp-line',
        glyphMarginClassName: 'bp-glyph',
        glyphMarginHoverMessage: { value: `Breakpoint at line ${l}` },
      }
    }))
  ]);

  SonificationManager.playTone(600, 0.1, 0.1);
  speak(`Breakpoint set at line ${lineNum}.`);
  srAnnounce(`Breakpoint line ${lineNum}`);
  out(`Breakpoints active: ${Array.from(_breakpoints).sort((a,b)=>a-b).join(', ')}`);
}

function clearBreakpoints() {
  _breakpoints.clear();
  _watchedVars.clear();
  _breakpointDecorations = editor.deltaDecorations(_breakpointDecorations, []);
  speak('All breakpoints cleared.');
  srAnnounce('Breakpoints cleared');
  out('All breakpoints removed.');
}

function watchVariable(varName) {
  if (!varName) { speak('Please specify a variable name to watch.'); return; }
  _watchedVars.add(varName);
  speak(`Now watching variable ${varName}. I will report its value at each breakpoint.`);
  srAnnounce(`Watching ${varName}`);
  out(`Watched variables: ${Array.from(_watchedVars).join(', ')}`);
}

function debugContinue() {
  // Walk the trace forward until we hit a breakpoint line
  const trace = window.executionTrace || [];
  if (!trace.length) { speak('No trace available. Run your code first.'); return; }

  // If the trace was truncated by the 5000-event cap AND we have unhit breakpoints,
  // warn the user that breakpoints past the truncation point are unreachable.
  const truncated = trace.some(e => e.type === 'overflow');
  if (truncated && _breakpoints.size > 0) {
    const bpLines = Array.from(_breakpoints).sort((a, b) => a - b);
    const linesHitInTrace = new Set(
      trace.filter(e => e.type === 'line_exec').map(e => e.line)
    );
    const unreachable = bpLines.filter(l => !linesHitInTrace.has(l));
    if (unreachable.length > 0) {
      speak(`Heads up: your trace was truncated at five thousand steps. Breakpoint${unreachable.length === 1 ? '' : 's'} at line ${unreachable.join(', line ')} may not be reachable. Try simplifying the loop and re-running.`);
    }
  }

  let idx = window.traceIndex || 0;
  let hitBreakpoint = false;

  while (idx < trace.length) {
    const event = trace[idx];
    idx++;
    if (event.type === 'line_exec' && _breakpoints.has(event.line)) {
      hitBreakpoint = true;
      window.traceIndex = idx;

      // Report watched variables at this breakpoint
      const stateEvents = trace.slice(0, idx).filter(e => e.type === 'state_change' && e.line === event.line);
      let varReport = '';
      if (_watchedVars.size > 0 && stateEvents.length > 0) {
        const lastState = stateEvents[stateEvents.length - 1];
        const relevant  = (lastState.changes || []).filter(c =>
          Array.from(_watchedVars).some(v => c.startsWith(v + ' '))
        );
        if (relevant.length) varReport = ' ' + relevant.join(', ');
      }

      SonificationManager.playTone(800, 0.15, 0.12);
      gotoLine(event.line, false);
      speak(`Hit breakpoint at line ${event.line}.${varReport || ''}`);
      srAnnounce(`Breakpoint hit line ${event.line}`);
      return;
    }
  }

  if (!hitBreakpoint) {
    window.traceIndex = 0;
    speak('No more breakpoints hit. Execution complete.');
    srAnnounce('Execution complete');
  }
}

// ---------- MENTOR / LEARNING MODE ----------

let _mentorActive = false;
let _currentQuiz  = null;

function startMentorMode() {
  _mentorActive = true;
  const lang = getLanguage();
  if (lang === 'hi') {
    speak('Learning mode शुरू हुआ। आप कह सकते हैं: quiz करो, bug challenge दो, या कोई concept समझाओ जैसे variables समझाओ।');
  } else {
    speak('Learning mode started. You can say: quiz me, bug challenge, or explain a concept — for example, explain loops.');
  }
  srAnnounce('Learning mode active');
  out('LEARNING MODE ACTIVE\n\nCommands:\n- "quiz me on loops"\n- "explain variables"\n- "bug challenge"\n- "explain conditionals"\n- "quiz me on functions"');
}

async function quizMe(topic) {
  SpeechManager.cancelAll();
  const t = topic || 'Python basics';
  showAI(`Creating quiz on ${t}...`);
  speak(`Creating a quiz question on ${t}.`);
  try {
    const res  = await fetch('/mentor/quiz', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ topic: t, language: getLanguage() }),
    });
    const data = await res.json();
    if (!data.success) { speak('Could not generate quiz. Try again.'); hideAI(); return; }

    const q = data.quiz;
    _currentQuiz = q;

    const display = `QUIZ: ${q.question}\n\n${q.options.join('\n')}\n\nSay "answer A", "answer B", or "answer C".`;
    out(display);
    srAnnounce('Quiz question ready');
    speak(q.question);
    q.options.forEach(o => speak(o));
    speak('Say answer A, answer B, or answer C.');

    // Store expected answer in per-tab state so other tabs don't intercept.
    // Expires after 5 minutes so a stale quiz doesn't catch later voice input.
    tabState()._pendingQuizAnswer = {
      answer: q.answer,
      explanation: q.explanation,
      expiresAt: Date.now() + 5 * 60 * 1000,
    };

  } catch (e) {
    console.error(e);
    speak('Quiz failed. Please try again.');
  } finally {
    hideAI();
  }
}

async function explainConcept(concept) {
  SpeechManager.cancelAll();
  const c = concept || 'variables';
  showAI(`Explaining ${c}...`);
  speak(`Explaining ${c}.`);
  try {
    const res  = await fetch('/mentor/explain', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ concept: c, language: getLanguage() }),
    });
    const data = await res.json();
    if (data.success) {
      out(data.explanation);
      speak(data.explanation);
      srAnnounce(`${c} explained`);
    } else {
      speak('Could not explain that concept. Try again.');
    }
  } catch (e) {
    console.error(e);
    speak('Explanation failed. Please try again.');
  } finally {
    hideAI();
  }
}

async function bugChallenge() {
  SpeechManager.cancelAll();
  showAI('Generating bug challenge...');
  speak('Generating a bug fixing challenge. Get ready.');
  try {
    const res  = await fetch('/mentor/bug-challenge', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ language: getLanguage() }),
    });
    const data = await res.json();
    if (!data.success) { speak('Could not generate challenge. Try again.'); hideAI(); return; }

    const ch = data.challenge;
    setCode(ch.code);
    out(`BUG CHALLENGE\n\nFind and fix the bug in the editor.\nHint: ${ch.hint}\n\nSay "show answer" when ready to reveal.`);
    srAnnounce('Bug challenge loaded');
    speak(`Bug challenge loaded into editor. ${ch.hint}. Say show answer when you are ready.`);

    // Store pending bug challenge in per-tab state so other tabs don't intercept.
    // Expires after 10 minutes so a stale challenge doesn't catch later voice input.
    tabState()._pendingBugChallenge = {
      bug: ch.bug,
      fixed: ch.fixed,
      expiresAt: Date.now() + 10 * 60 * 1000,
    };

  } catch (e) {
    console.error(e);
    speak('Challenge failed. Please try again.');
  } finally {
    hideAI();
  }
}

function restartTutorial() {
  if (window.TutorialController) {
    window.TutorialController.open();
    speak('Tutorial restarted from the beginning.');
  }
}

function showInputDialog(promptText, callback) {
  // window.prompt is inaccessible to screen readers — use an inline modal instead
  const existing = document.getElementById('_cuInputDialog');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = '_cuInputDialog';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', promptText);
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:30000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px);';

  overlay.innerHTML = `
    <div style="background:var(--bg-panel);border:1px solid var(--border-strong);border-radius:12px;padding:24px;min-width:280px;max-width:400px;width:90%;color:var(--text-main);">
      <label id="_cuDialogLabel" style="display:block;color:var(--text-main);margin-bottom:12px;font-family:inherit;font-size:0.9rem;">${promptText}</label>
      <input id="_cuDialogInput" type="text" aria-labelledby="_cuDialogLabel"
             style="width:100%;padding:8px 12px;border-radius:6px;border:1px solid var(--border-soft);background:var(--bg-soft);color:var(--text-main);font-family:inherit;font-size:1rem;margin-bottom:12px;"
      />
      <div style="display:flex;gap:8px;justify-content:flex-end;">
        <button id="_cuDialogCancel" style="padding:8px 16px;border-radius:6px;border:1px solid var(--border-soft);background:var(--bg-soft);color:var(--text-main);cursor:pointer;font-family:inherit;">Cancel</button>
        <button id="_cuDialogOk"     style="padding:8px 16px;border-radius:6px;border:none;background:var(--accent);color:#fff;font-weight:600;cursor:pointer;font-family:inherit;">Go</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);
  const input  = document.getElementById('_cuDialogInput');
  const ok     = document.getElementById('_cuDialogOk');
  const cancel = document.getElementById('_cuDialogCancel');

  function confirm() {
    const val = input.value.trim();
    overlay.remove();
    if (editor) editor.focus();
    if (val) callback(parseInt(val, 10) || 1);
  }
  function dismiss() {
    overlay.remove();
    if (editor) editor.focus();
    speak('Cancelled.');
  }

  ok.addEventListener('click', confirm);
  cancel.addEventListener('click', dismiss);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); confirm(); }
    if (e.key === 'Escape') { e.preventDefault(); dismiss(); }
  });
  overlay.addEventListener('click', e => { if (e.target === overlay) dismiss(); });

  requestAnimationFrame(() => {
    input.focus();
    speak(promptText + '. Type a number and press Enter, or press Escape to cancel.');
  });
}
// ---------- LIST VARIABLES WITH VALUES (from execution trace) ----------
async function listVariablesWithValues() {
  const trace = window.executionTrace || [];
  if (!trace.length) {
    speak('No variables to report yet. Please run your code first by pressing Control Enter or saying "run".');
    out('No execution trace available. Run your code first.');
    return;
  }
  // Walk trace forward, building current variable values from state_change events
  const vars = {};
  for (const event of trace) {
    if (event.type === 'state_change' && event.changes) {
      for (const change of event.changes) {
        // Match: "x changed from 0 to 5" or "x initialized to 5"
        const initMatch = change.match(/^(\w+) initialized to (.+)$/);
        const changeMatch = change.match(/^(\w+) changed from .+ to (.+)$/);
        if (initMatch) vars[initMatch[1]] = initMatch[2];
        else if (changeMatch) vars[changeMatch[1]] = changeMatch[2];
      }
    }
  }
  const names = Object.keys(vars);
  if (!names.length) {
    speak('Your code ran but no variables were declared.');
    out('No variables found in execution trace.');
    return;
  }
  let display = `VARIABLES AND VALUES (${names.length}):\n\n`;
  let speech = `You have ${names.length} variable${names.length === 1 ? '' : 's'}. `;
  for (const name of names) {
    display += `  ${name} = ${vars[name]}\n`;
    speech += `${pronounceVariableJS(name)} equals ${vars[name]}. `;
  }
  out(display);
  speak(speech);
}

// Lightweight phonetic helper for single letters (NATO-style for screen readers)
function pronounceVariableJS(name) {
  if (!name || name.length !== 1) return name;
  const map = {a:'a',b:'bee',c:'see',d:'dee',e:'ee',f:'eff',g:'gee',h:'aitch',i:'eye',j:'jay',k:'kay',l:'ell',m:'em',n:'en',o:'oh',p:'pee',q:'cue',r:'arr',s:'ess',t:'tee',u:'you',v:'vee',w:'double-you',x:'ex',y:'why',z:'zee'};
  return map[name.toLowerCase()] || name;
}

// ---------- WALK THROUGH CODE (sonify + narrate every line) ----------
let _walkActive = false;

async function walkThroughCode() {
  if (_walkActive) {
    _walkActive = false;
    SpeechManager.cancelAll();
    SonificationManager.clearAll();
    speak('Walkthrough stopped.');
    return;
  }
  const model = getModel();
  if (!model) { speak('Editor not ready.'); return; }
  const code = getCode();
  if (!code.trim()) { speak('The editor is empty. Write some code first.'); return; }

  _walkActive = true;
  SpeechManager.cancelAll();
  await sleep(400);

  // Wait for the speech engine to fully drain before starting
  let drainAttempts = 0;
  while (window.speechSynthesis && window.speechSynthesis.speaking && drainAttempts < 20) {
    await sleep(100);
    drainAttempts++;
  }

  // STEP 1: Show the full code in the output box up front so the user
  // (or a sighted helper) can see/read the whole program before narration.
  const lines = code.split('\n');
  const fullCodeDisplay = 'WALKING THROUGH YOUR CODE:\n\n' +
    lines.map((l, i) => `${i + 1}: ${l}`).join('\n') +
    '\n\n--- NARRATION ---\n';
  out(fullCodeDisplay);

  speak('Walking through your code. Press Escape to stop at any time.');
  await sleep(500);
  drainAttempts = 0;
  while (window.speechSynthesis && window.speechSynthesis.speaking && drainAttempts < 30) {
    await sleep(100);
    drainAttempts++;
  }

  // STEP 2: Narrate each line. APPEND descriptions to the output box
  // instead of replacing it, so the full code stays visible.
  const outputEl = document.getElementById('output');
  let narrationLog = '';

  for (let i = 0; i < lines.length; i++) {
    if (!_walkActive) return;
    const line = lines[i];
    const lineNum = i + 1;
    const trimmed = line.trim();

    try {
      editor.setPosition({ lineNumber: lineNum, column: 1 });
      editor.revealLineInCenter(lineNum);
    } catch (e) {}

    const indent = Math.floor(getIndentLevel(line));

    // Build description (same logic as before)
    let desc;
    if (!trimmed) {
      desc = `Line ${lineNum}: blank line.`;
    } else if (trimmed.startsWith('#')) {
      desc = `Line ${lineNum}, comment: ${trimmed.replace(/^#\s*/, '')}.`;
    } else if (trimmed.startsWith('def ')) {
      const m = trimmed.match(/^def\s+(\w+)\(([^)]*)\)/);
      if (m) {
        const params = m[2].trim();
        desc = `Line ${lineNum}, defines function ${m[1]}` + (params ? ` taking ${params}.` : ' with no parameters.');
      } else {
        desc = `Line ${lineNum}, function definition: ${trimmed}.`;
      }
    } else if (trimmed.startsWith('class ')) {
      const m = trimmed.match(/^class\s+(\w+)/);
      desc = m ? `Line ${lineNum}, defines class ${m[1]}.` : `Line ${lineNum}, class definition.`;
    } else if (trimmed.startsWith('for ')) {
      desc = `Line ${lineNum}, for loop: ${trimmed.replace(/^for\s+/, '').replace(/:$/, '')}.`;
    } else if (trimmed.startsWith('while ')) {
      desc = `Line ${lineNum}, while loop: ${trimmed.replace(/^while\s+/, '').replace(/:$/, '')}.`;
    } else if (trimmed.startsWith('if ')) {
      desc = `Line ${lineNum}, if condition: ${trimmed.replace(/^if\s+/, '').replace(/:$/, '')}.`;
    } else if (trimmed.startsWith('elif ')) {
      desc = `Line ${lineNum}, else if: ${trimmed.replace(/^elif\s+/, '').replace(/:$/, '')}.`;
    } else if (trimmed.startsWith('else')) {
      desc = `Line ${lineNum}, else branch.`;
    } else if (trimmed.startsWith('return')) {
      desc = `Line ${lineNum}, returns: ${trimmed.replace(/^return\s*/, '') || 'nothing'}.`;
    } else if (trimmed.startsWith('import ') || trimmed.startsWith('from ')) {
      desc = `Line ${lineNum}, ${trimmed}.`;
    } else if (/^\w+\s*=/.test(trimmed)) {
      const m = trimmed.match(/^(\w+)\s*=\s*(.+)$/);
      desc = m ? `Line ${lineNum}, assigns ${m[1]} to ${m[2]}.` : `Line ${lineNum}: ${trimmed}.`;
    } else if (trimmed.startsWith('print(')) {
      desc = `Line ${lineNum}, prints: ${trimmed.replace(/^print\(/, '').replace(/\)$/, '')}.`;
    } else {
      desc = `Line ${lineNum}: ${trimmed}.`;
    }

    // APPEND, don't replace — full code + accumulated narration stays visible
    narrationLog += desc + '\n';
    if (outputEl) {
      outputEl.textContent = fullCodeDisplay + narrationLog;
    }

    sonifyLine(line, indent);
    await sleep(300);
    if (!_walkActive) return;

    await SpeechManager.enqueue(desc);
    if (!_walkActive) return;

    let postSpeakAttempts = 0;
    while (window.speechSynthesis && window.speechSynthesis.speaking && _walkActive && postSpeakAttempts < 60) {
      await sleep(100);
      postSpeakAttempts++;
    }
    if (!_walkActive) return;

    await sleep(400);
    if (!_walkActive) return;
  }

  if (_walkActive) {
    _walkActive = false;
    speak('Walkthrough complete.');
    if (outputEl) {
      outputEl.textContent = fullCodeDisplay + narrationLog + '\nWalkthrough complete.';
    }
  }
}