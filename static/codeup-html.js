'use strict';

(function () {
  const starterHtml = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>My CodeUp Website</title>
  <style>
    :root { color-scheme: light; }
    body {
      margin: 0;
      font-family: Arial, sans-serif;
      color: #111827;
      background: #ffffff;
    }
    header {
      padding: 24px;
      border-bottom: 1px solid #cbd5e1;
      background: #f8fafc;
    }
    main {
      max-width: 960px;
      margin: 0 auto;
      padding: 28px 20px;
    }
    section {
      margin: 18px 0;
      padding: 16px;
      border: 1px solid #cbd5e1;
      background: white;
    }
    button {
      padding: 10px 14px;
      border: 1px solid #0f766e;
      color: white;
      background: #0f766e;
      cursor: pointer;
    }
  </style>
</head>
<body>
  <header>
    <h1>My First CodeUp Website</h1>
    <p>Edit this HTML or ask CodeUp to build a new website.</p>
  </header>
  <main>
    <section>
      <h2>About</h2>
      <p>This page is pure HTML, CSS, and a little JavaScript. Press Preview to host it locally.</p>
      <button type="button" onclick="alert('You made the page interactive!')">Try me</button>
    </section>
  </main>
</body>
</html>`;
  const starterBodyHtml = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>My CodeUp Website</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header class="site-header">
    <h1>My CodeUp Website</h1>
    <p>Edit index.html, style.css, and script.js, or say "generate a website for my robotics lab".</p>
    <button id="cta" type="button">Say hello</button>
  </header>
  <main>
    <section>
      <h2>About</h2>
      <p>This page is built from three files: HTML for structure, CSS for style, and JavaScript for behaviour.</p>
    </section>
  </main>
  <script src="script.js" defer></script>
</body>
</html>`;

  const starterCss = `:root { color-scheme: light; --accent: #2563eb; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height: 1.6; color: #111827; background: #ffffff; }
.site-header { padding: 24px; border-bottom: 1px solid #cbd5e1; background: #f8fafc; }
.site-header h1 { font-size: 2rem; margin: 0 0 .5rem; }
main { max-width: 820px; margin: 0 auto; padding: 24px 20px; }
section { background: #fff; border: 1px solid #cbd5e1; padding: 16px; }
button { font: inherit; font-weight: 600; cursor: pointer; margin-top: 14px; padding: 9px 14px; border: 1px solid var(--accent); color: #fff; background: var(--accent); }
button:focus-visible { outline: 3px solid #312e81; outline-offset: 3px; }`;

  const starterJs = `var cta = document.getElementById('cta');
if (cta) {
  cta.addEventListener('click', function () {
    cta.textContent = 'Hello!';
  });
}`;

  const starterPython = `total = 0
for number in range(3):
    total = total + number
    print(total)`;

  const PYTHON_INPUT_LIMIT = 50;
  const PYTHON_INPUT_CHAR_LIMIT = 1000;

  const PYTHON_EXAMPLES = {
    variables: {
      label: 'variables',
      code: `name = "Amit"
score = 4
print(name)
print(score)`,
    },
    loop: {
      label: 'loop',
      code: `total = 0
for i in range(1, 5):
    total = total + i
    print(total)`,
    },
    input: {
      label: 'input',
      code: `name = input("Name: ")
print("Hello", name)`,
    },
    function: {
      label: 'function',
      code: `def add(a, b):
    return a + b

result = add(2, 3)
print(result)`,
    },
    condition: {
      label: 'condition',
      code: `total = 12
if total > 10:
    print("large")
else:
    print("small")`,
    },
  };

  const starterFiles = { html: starterBodyHtml, css: starterCss, js: starterJs };

  const state = {
    activeRecognition: null,
    wakeRecognition: null,
    activeVoice: false,
    wakeListening: false,
    paused: false,
    manualVoiceStop: false,
    demoMode: false,
    lastSpoken: '',
    lastUrl: '',
    lastReview: '',
    memory: { history: [], last_html: '', last_url: '', last_review: '' },
    audioCtx: null,
    wakeWord: (localStorage.getItem('codeup_wake_word') || 'hey codeup').toLowerCase(),
    wakeUntil: 0,
    navigator: { items: [], index: -1 },
    versions: [],
    pages: {},
    currentPage: 'home',
    projectId: '',
    projectName: 'Untitled Project',
    autosaveTimer: null,
    lastAudit: null,
    originalGenerationRequest: '',
    currentFiles: { html: '', css: '', js: '' },
    lastEditRequest: '',
    lastEditSummary: '',
    exportStatus: '',
    lastCommand: '',
    lastOutput: '',
    heartbeatTimer: null,
    heartbeatLabel: '',
    heartbeatToken: 0,
    asyncToken: 0,
    replay: { before: null, after: null },
    watchpointRules: [],
    lastPauseReason: '',
    lastCodeMap: '',
    lastStepNarration: '',
    lastLearningNotes: '',
    lastAccessibilityMap: '',
    lastFileExplanation: '',
    lastProjectReview: '',
    lastPreviewDescription: '',
    lastProjectSummary: '',
    lastPythonError: '',
    lastPythonRun: null,
    lastPythonStepCursor: 0,
    lastPythonStateWatch: null,
    pythonInputs: Array.isArray(loadJsonStore('codeup_python_inputs', [])) ? loadJsonStore('codeup_python_inputs', []) : [],
    pythonHistory: Array.isArray(loadJsonStore('codeup_python_history', [])) ? loadJsonStore('codeup_python_history', []) : [],
    projectType: 'generic_website',
    speechQueue: [],
    tutorial: {
      active: false,
      modules: [],
      index: 0,
      current: '',
      lastValidation: null,
    },
    track: { active: false, id: '', index: 0, steps: [], title: '' },
    generationWizard: { active: false, index: 0, answers: {} },
    guidedProjects: null,
    guidedProject: loadJsonStore('codeup_guided_project', null),
    tracks: null,
    teacherSuggestions: [],
    walkthrough: {
      active: false,
      mode: null,
      journeyElements: [],
      journeyIndex: -1,
      watchpointMode: false,
      watchpoints: [],
      watchpointIndex: 0,
      htmlBeforeFix: '',
      currentIssueIndex: 0,
    },
  };

  const pageTemplates = {
    'school event': { title: 'School Event', sections: ['About the Event', 'Schedule', 'How to Join'] },
    'club page': { title: 'Club Page', sections: ['About the Club', 'Meetings', 'Join Us'] },
    'personal portfolio': { title: 'Personal Portfolio', sections: ['About Me', 'Projects', 'Contact'] },
    'charity drive': { title: 'Charity Drive', sections: ['Our Goal', 'What We Need', 'Volunteer'] },
    'science project': { title: 'Science Project', sections: ['Question', 'Experiment', 'Results'] },
  };

  function $(id) { return document.getElementById(id); }
  function lang() { return ($('languageSelector') || {}).value || 'en'; }
  function isHindi() { return lang() === 'hi'; }
  function t(en, hi) { return isHindi() ? hi : en; }

  function announce(message) {
    const sr = $('srAnnouncer');
    if (sr && message) sr.textContent = message;
  }

  function cancelSpeech() {
    try { window.speechSynthesis.cancel(); } catch (error) {}
  }

  function detectSpeakLang(text) {
    if (window.VoiceMemoryEngine) return window.VoiceMemoryEngine.detectLang(text);
    return isHindi() ? 'hi-IN' : 'en-US';
  }

  function speak(text, opts = {}) {
    if (!text) return;
    cancelSpeech();
    state.lastSpoken = text;
    announce(text);
    if (opts.silent) return;
    if (!('speechSynthesis' in window)) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = detectSpeakLang(text);
    utterance.rate = opts.rate || 1;
    utterance.pitch = opts.pitch || 1;
    window.speechSynthesis.speak(utterance);
  }

  function speakChunked(text) {
    const clean = (text || '').replace(/\s+/g, ' ').trim();
    if (!clean) return;
    const chunks = [];
    let remaining = clean;
    while (remaining.length > 700) {
      let splitAt = remaining.lastIndexOf('. ', 700);
      if (splitAt < 240) splitAt = remaining.lastIndexOf(' ', 700);
      if (splitAt < 240) splitAt = 700;
      chunks.push(remaining.slice(0, splitAt + 1).trim());
      remaining = remaining.slice(splitAt + 1).trim();
    }
    if (remaining) chunks.push(remaining);
    state.speechQueue = chunks.slice(1);
    speak(chunks[0] + (state.speechQueue.length ? ' Say "say more" to continue.' : ''));
  }

  function speakMore() {
    const next = state.speechQueue.shift();
    if (!next) {
      speak('No more spoken explanation is queued.');
      return true;
    }
    speak(next + (state.speechQueue.length ? ' Say "say more" to continue.' : ''));
    return true;
  }

  window.speak = speak;

  function writeOutput(message, shouldSpeak = false) {
    const output = $('output');
    if (output) output.textContent = message;
    const empty = $('outputEmpty');
    if (empty && (message || '').trim()) empty.hidden = true;
    state.lastOutput = message || '';
    if (shouldSpeak) speak(message);
  }

  function clearOutput() {
    const output = $('output');
    if (output) output.textContent = '';
    const empty = $('outputEmpty');
    if (empty) empty.hidden = false;
    state.lastOutput = '';
    announce('Output cleared.');
  }

  function readOutput() {
    const text = (($('output') || {}).textContent || state.lastOutput || '').trim();
    speak(text || 'There is no output to read yet.');
  }

  function slugify(value) {
    return (value || 'codeup-site').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'codeup-site';
  }

  function loadJsonStore(key, fallback) {
    try {
      const value = JSON.parse(localStorage.getItem(key) || '');
      return value && typeof value === 'object' ? value : fallback;
    } catch (error) {
      return fallback;
    }
  }

  function saveJsonStore(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (error) {}
  }

  function nextAsyncToken() {
    state.asyncToken += 1;
    return state.asyncToken;
  }

  function isAsyncFresh(token) {
    return token === state.asyncToken;
  }

  function softSpeak(text) {
    if (!text || document.body.classList.contains('theme-reduced-motion')) return;
    if (!('speechSynthesis' in window) || window.speechSynthesis.speaking) return;
    try {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = detectSpeakLang(text);
      utterance.rate = 0.95;
      window.speechSynthesis.speak(utterance);
    } catch (error) {}
  }

  function startHeartbeat(label) {
    stopHeartbeat();
    const token = nextAsyncToken();
    state.heartbeatToken = token;
    state.heartbeatLabel = label || 'Working';
    let count = 0;
    state.heartbeatTimer = setInterval(() => {
      if (token !== state.heartbeatToken) return;
      count += 1;
      const msg = `${state.heartbeatLabel}... still working.`;
      announce(msg);
      if (count % 2 === 1) softSpeak(msg);
    }, 9000);
    return token;
  }

  function stopHeartbeat(token) {
    if (token && token !== state.heartbeatToken) return;
    if (state.heartbeatTimer) clearInterval(state.heartbeatTimer);
    state.heartbeatTimer = null;
    state.heartbeatLabel = '';
    state.heartbeatToken = 0;
  }

  const CODEUP_CSS_ID = 'codeup-ide-css';
  const CODEUP_JS_ID = 'codeup-ide-js';
  const MONACO_LANGUAGES = {
    htmlEditor: 'html',
    cssEditor: 'css',
    jsEditor: 'javascript',
    pythonEditor: 'python',
  };

  function getEditor() { return $('htmlEditor'); }
  function getCssEditor() { return $('cssEditor'); }
  function getJsEditor() { return $('jsEditor'); }
  function getPythonEditor() { return $('pythonEditor'); }
  function getHtmlSource() { return (getEditor() || {}).value || ''; }
  function getCss() { const el = getCssEditor(); return el ? el.value : ''; }
  function getJs() { const el = getJsEditor(); return el ? el.value : ''; }
  function getPython() { const el = getPythonEditor(); return el ? el.value : ''; }
  function stripManagedBlocks(html) {
    return String(html || '')
      .replace(new RegExp('\\s*<style\\b[^>]*id=["\\\']?' + CODEUP_CSS_ID + '["\\\']?[^>]*>[\\s\\S]*?<\\/style>', 'gi'), '')
      .replace(new RegExp('\\s*<script\\b[^>]*id=["\\\']?' + CODEUP_JS_ID + '["\\\']?[^>]*>[\\s\\S]*?<\\/script>', 'gi'), '');
  }
  function stripExternalRefs(html) {
    return String(html || '')
      .replace(/\s*<link\b[^>]*href=["']?(?:\.\/)?style\.css["']?[^>]*>/gi, '')
      .replace(/\s*<script\b[^>]*src=["']?(?:\.\/)?script\.js["']?[^>]*>\s*<\/script>/gi, '');
  }
  function ensureManagedRefs(html, hasCss, hasJs) {
    let doc = normalizeHtmlDocument(html);
    if (hasCss && !/<link\b[^>]*href=["']?(?:\.\/)?style\.css["']?/i.test(doc)) {
      const link = '\n  <link rel="stylesheet" href="style.css">';
      doc = /<\/head\s*>/i.test(doc) ? doc.replace(/<\/head\s*>/i, () => link + '\n</head>') : link + doc;
    }
    if (hasJs && !/<script\b[^>]*src=["']?(?:\.\/)?script\.js["']?/i.test(doc)) {
      const script = '\n  <script src="script.js" defer></script>';
      doc = /<\/body\s*>/i.test(doc) ? doc.replace(/<\/body\s*>/i, () => script + '\n</body>') : doc + script;
    }
    return doc;
  }
  function combineDocument(html, css, js) {
    let doc = normalizeHtmlDocument(stripExternalRefs(stripManagedBlocks(html)));
    if (css && css.trim()) {
      const styleBlock = '\n<style id="' + CODEUP_CSS_ID + '">\n' + css.trim() + '\n</style>\n';
      doc = /<\/head\s*>/i.test(doc)
        ? doc.replace(/<\/head\s*>/i, () => styleBlock + '</head>')
        : styleBlock + doc;
    }
    if (js && js.trim()) {
      const scriptBlock = '\n<script id="' + CODEUP_JS_ID + '">\n' + js.trim() + '\n</script>\n';
      doc = /<\/body\s*>/i.test(doc)
        ? doc.replace(/<\/body\s*>/i, () => scriptBlock + '</body>')
        : doc + scriptBlock;
    }
    return doc;
  }
  function splitDocument(doc) {
    const source = String(doc || '');
    let css = '';
    let js = '';
    const cssMatch = source.match(
      new RegExp('<style\\b[^>]*id=["\\\']?' + CODEUP_CSS_ID + '["\\\']?[^>]*>([\\s\\S]*?)<\\/style>', 'i'),
    );
    if (cssMatch) css = cssMatch[1].trim();
    const jsMatch = source.match(
      new RegExp('<script\\b[^>]*id=["\\\']?' + CODEUP_JS_ID + '["\\\']?[^>]*>([\\s\\S]*?)<\\/script>', 'i'),
    );
    if (jsMatch) js = jsMatch[1].trim();
    let html = stripManagedBlocks(source);
    if (css || js) html = ensureManagedRefs(html, !!css, !!js);
    return { html, css, js };
  }
  function editorValue(editor) {
    if (!editor) return '';
    if (editor.__codeupMonacoEditor && typeof editor.__codeupMonacoEditor.getValue === 'function') {
      return editor.__codeupMonacoEditor.getValue();
    }
    return editor.value || '';
  }

  function setEditorValue(editor, value) {
    if (!editor) return;
    const nextValue = String(value || '');
    editor.value = nextValue;
    if (editor.__codeupMonacoEditor && typeof editor.__codeupMonacoEditor.setValue === 'function') {
      editor.__codeupMonacoEditor.setValue(nextValue);
    }
  }

  function getHtml() {
    const html = getHtmlSource();
    const css = getCss();
    const js = getJs();
    if ((css && css.trim()) || (js && js.trim())) return combineDocument(html, css, js);
    return html;
  }

  function persistDrafts() {
    try {
      const h = getEditor(); if (h) sessionStorage.setItem('codeup_html_draft', editorValue(h));
      const c = getCssEditor(); if (c) sessionStorage.setItem('codeup_css_draft', editorValue(c));
      const j = getJsEditor(); if (j) sessionStorage.setItem('codeup_js_draft', editorValue(j));
      const p = getPythonEditor(); if (p) sessionStorage.setItem('codeup_python_draft', editorValue(p));
      localStorage.setItem('codeup_last_work', JSON.stringify({
        html: h ? editorValue(h) : '',
        css: c ? editorValue(c) : '',
        js: j ? editorValue(j) : '',
        python: p ? editorValue(p) : '',
        projectId: state.projectId,
        projectName: state.projectName,
        currentPage: state.currentPage,
        previewUrl: state.lastUrl,
        savedAt: new Date().toISOString(),
      }));
    } catch (error) {}
  }
  function loadGeneratedFiles(files) {
    const htmlEl = getEditor();
    const cssEl = getCssEditor();
    const jsEl = getJsEditor();
    const css = files.css || '';
    const js = files.js || '';
    const html = ensureManagedRefs(stripManagedBlocks(normalizeHtmlDocument(files.html || '')), !!css.trim(), !!js.trim());
    if (cssEl || jsEl) {
      setEditorValue(htmlEl, html);
      setEditorValue(cssEl, css);
      setEditorValue(jsEl, js);
    } else if (htmlEl) {
      setEditorValue(htmlEl, combineDocument(html, css, js));
    }
    persistDrafts();
    state.pages[state.currentPage] = getHtml();
    state.currentFiles = { html, css, js };
    scheduleAutosave();
  }

  function activePages() {
    state.pages[state.currentPage] = getHtml();
    return Object.fromEntries(Object.entries(state.pages).filter(([, value]) => value && value.trim()));
  }

  function updateProjectUi() {
    const name = $('projectNameInput');
    if (name && name.value !== state.projectName) name.value = state.projectName;
    const select = $('projectSelect');
    if (select && state.projectId) select.value = state.projectId;
  }

  function snapshotVersion(note, summary) {
    const html = getHtml();
    const css = getCss();
    const js = getJs();
    if (!html) return;
    const last = state.versions[state.versions.length - 1];
    if (last && last.html === html && last.css === css && last.js === js) return;
    const version = {
      id: '',
      html,
      css,
      js,
      note: note || 'Edited website',
      label: note || 'Edited website',
      source: 'frontend',
      command: state.lastCommand || '',
      page: state.currentPage,
      timestamp: new Date().toISOString(),
      summary: summary || [],
    };
    state.versions.push(version);
    state.versions = state.versions.slice(-25);
    persistVersions();
    saveVersionToServer(version);
  }

  function sourceSnapshot(label) {
    return {
      label: label || 'Current code',
      html: getHtmlSource(),
      css: getCss(),
      js: getJs(),
      combined: getHtml(),
      time: new Date().toISOString(),
    };
  }

  function beginReplay(label) {
    state.replay.before = sourceSnapshot(label || 'Before change');
  }

  function finishReplay(label) {
    state.replay.after = sourceSnapshot(label || 'After change');
    if (!/generation/i.test(label || '')) {
      state.editHappened = true;
      state.lastEditInstruction = state.lastCommand || (state.commandHistory || []).slice(-1)[0] || state.lastEditInstruction || '';
    }
    persistDrafts();
  }
  function exportChangeReplay() {
    if (!state.editHappened) return null;
    const before = state.replay && state.replay.before;
    if (!before) return null;
    const after = (state.replay && state.replay.after) || sourceSnapshot('Current code');
    return {
      html_before: before.html,
      html_after: after.html,
      css_before: before.css,
      css_after: after.css,
      js_before: before.js,
      js_after: after.js,
      instruction: state.lastEditInstruction || '',
    };
  }

  function versionSourceSnapshot(version, label) {
    return {
      label: label || version.label || version.note || 'Saved version',
      html: version.html || '',
      css: version.css || '',
      js: version.js || '',
      combined: version.combined || version.html || '',
      time: version.timestamp || '',
    };
  }

  function latestVersionPair() {
    const versions = (state.versions || []).filter(item => item && (item.html || item.css || item.js));
    if (versions.length < 2) return null;
    return {
      before: versionSourceSnapshot(versions[versions.length - 2], 'Before change'),
      after: versionSourceSnapshot(versions[versions.length - 1], 'After change'),
    };
  }

  function latestReplayPair() {
    if (state.replay && state.replay.before) {
      return {
        before: state.replay.before,
        after: state.replay.after || sourceSnapshot('Current code'),
      };
    }
    return latestVersionPair();
  }

  function changeReviewMode(reason) {
    const lower = (reason || '').toLowerCase();
    if (lower.includes('read before and after') || lower.includes('compare before and after')) return 'before_after';
    if (lower.includes('risky') || lower.includes('risk')) return 'risk';
    if (lower.includes('explain this change') || lower.includes('why does the fixed version work')) return 'explain';
    return 'summary';
  }
  function suggestNext(suggestions) {
    const list = (suggestions || []).filter(Boolean);
    const region = $('tryNext');
    if (!region) {
      const output = $('output');
      if (list.length && output && (output.textContent || '').trim()) {
        output.textContent += `\n\nTry this next: ${list.map((item) => `"${item}"`).join(', ')}.`;
        state.lastOutput = output.textContent;
      }
      return;
    }
    region.innerHTML = '';
    if (!list.length) { region.hidden = true; return; }
    region.hidden = false;
    const label = document.createElement('span');
    label.className = 'ide-trynext-label';
    label.textContent = 'Try this next:';
    region.appendChild(label);
    list.forEach((cmd) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'ide-chip ide-chip-trynext';
      chip.setAttribute('data-cmd', cmd);
      chip.textContent = cmd;
      region.appendChild(chip);
    });
  }

  async function narrateReplay(reason, title) {
    const pair = latestReplayPair();
    if (!pair || !pair.before) {
      writeOutput(t('Nothing to compare yet. Make an edit first, then ask what changed.', 'Abhi compare karne ke liye kuch nahi hai. Pehle edit kariye, phir poochiye kya badla.'), true);
      return;
    }
    const before = pair.before;
    const after = pair.after || sourceSnapshot('Current code');
    const token = nextAsyncToken();
    try {
      const data = await apiJson('/mistake-replay', {
        method: 'POST',
        body: JSON.stringify({
          html_before: before.html,
          html_after: after.html,
          css_before: before.css,
          css_after: after.css,
          js_before: before.js,
          js_after: after.js,
          reason: reason || '',
          mode: changeReviewMode(reason),
        }),
      });
      if (!isAsyncFresh(token)) return;
      const message = title ? data.message.replace(/^Mistake replay:/, `${title}:`) : data.message;
      writeOutput(message, true);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      writeOutput(error.message, true);
    }
  }
  function setHtml(html) {
    const editor = getEditor();
    const cssEl = getCssEditor();
    const jsEl = getJsEditor();
    if (cssEl || jsEl) {
      const parts = splitDocument(html);
      setEditorValue(editor, parts.html);
      setEditorValue(cssEl, parts.css);
      setEditorValue(jsEl, parts.js);
      persistDrafts();
      state.pages[state.currentPage] = getHtml();
      state.currentFiles = { html: parts.html, css: parts.css, js: parts.js };
      scheduleAutosave();
    } else if (editor) {
      setEditorValue(editor, html);
      try { sessionStorage.setItem('codeup_html_draft', html); } catch (error) {}
      state.pages[state.currentPage] = html;
      state.currentFiles = { html, css: '', js: '' };
      scheduleAutosave();
    }
  }

  function restoreVersions() {
    try {
      const saved = JSON.parse(sessionStorage.getItem('codeup_versions') || '[]');
      if (Array.isArray(saved)) state.versions = saved.filter(item => item && item.html);
    } catch (error) {}
  }

  function persistVersions() {
    try { sessionStorage.setItem('codeup_versions', JSON.stringify(state.versions)); } catch (error) {}
  }

  async function apiJson(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    let data;
    try {
      data = await response.json();
    } catch (e) {
      throw new Error(`Server error (${response.status}). Please try again.`);
    }
    if (!data.success) throw new Error(data.error || 'Request failed.');
    return data;
  }

  async function apiJsonLoose(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    });
    let data;
    try {
      data = await response.json();
    } catch (e) {
      throw new Error(`Server error (${response.status}). Please try again.`);
    }
    if (!response.ok && data.success !== false) throw new Error(data.error || `Server error (${response.status}).`);
    return data;
  }

  async function refreshProjectList() {
    try {
      const data = await apiJson('/projects');
      const select = $('projectSelect');
      if (!select) return data.projects || [];
      select.innerHTML = '';
      for (const project of data.projects || []) {
        const option = document.createElement('option');
        option.value = project.id;
        option.textContent = project.name;
        select.appendChild(option);
      }
      updateProjectUi();
      return data.projects || [];
    } catch (error) {
      return [];
    }
  }

  async function openProject(projectId) {
    if (!projectId) return;
    const data = await apiJson(`/projects/${encodeURIComponent(projectId)}`);
    const project = data.project;
    state.projectId = project.id;
    state.projectName = project.name || 'Untitled Project';
    state.projectType = 'generic_website';
    state.pages = project.pages || {};
    state.currentPage = project.current_page || Object.keys(state.pages)[0] || 'home';
    if (!state.pages[state.currentPage]) state.pages[state.currentPage] = starterHtml;
    setHtml(state.pages[state.currentPage]);
    state.versions = (project.versions || []).map((version) => ({
      id: version.id,
      html: (version.pages || {})[version.current_page || state.currentPage] || Object.values(version.pages || {})[0] || '',
      pages: version.pages || {},
      note: version.label,
      label: version.label,
      source: version.source,
      page: version.current_page || 'home',
      timestamp: version.timestamp,
      summary: version.summary || [],
    })).filter(item => item.html);
    persistVersions();
    updateProjectUi();
    writeOutput(`Opened project: ${state.projectName}.`, false);
  }

  async function ensureProject() {
    const projects = await refreshProjectList();
    if (state.projectId) return;
    if (projects.length) {
      await openProject(projects[0].id);
      return;
    }
    const data = await apiJson('/projects', {
      method: 'POST',
      body: JSON.stringify({ name: state.projectName, html: getHtml() || starterHtml, current_page: state.currentPage }),
    });
    state.projectId = data.project.id;
    state.projectName = data.project.name;
    state.pages = data.project.pages || { home: getHtml() || starterHtml };
    await refreshProjectList();
    updateProjectUi();
  }

  function scheduleAutosave() {
    if (!state.projectId) return;
    clearTimeout(state.autosaveTimer);
    state.autosaveTimer = setTimeout(() => {
      saveProjectDraft().catch(() => {});
    }, 700);
  }

  async function saveProjectDraft() {
    if (!state.projectId) return;
    const pages = activePages();
    const name = ($('projectNameInput') || {}).value || state.projectName;
    const data = await apiJson(`/projects/${encodeURIComponent(state.projectId)}/autosave`, {
      method: 'POST',
      body: JSON.stringify({ pages, current_page: state.currentPage, name }),
    });
    state.projectName = data.project.name || state.projectName;
    updateProjectUi();
  }

  async function saveVersionToServer(version) {
    if (!state.projectId) return;
    try {
      const data = await apiJson(`/projects/${encodeURIComponent(state.projectId)}/versions`, {
        method: 'POST',
        body: JSON.stringify({
          label: version.label || version.note,
          source: version.source || 'frontend',
          pages: activePages(),
          current_page: state.currentPage,
          summary: version.summary || [],
        }),
      });
      version.id = data.version.id;
    } catch (error) {}
  }

  async function restoreVersionFromServer(versionId) {
    if (!state.projectId || !versionId) return false;
    try {
      const data = await apiJson(`/projects/${encodeURIComponent(state.projectId)}/versions/${encodeURIComponent(versionId)}/restore`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      await openProject(data.project.id);
      return true;
    } catch (error) {
      return false;
    }
  }

  function normalizeHtmlDocument(html) {
    const source = String(html || '').trim();
    const headMarkup = '<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>CodeUp Site</title></head>';
    if (!/<html\b/i.test(source)) {
      const fragment = source.replace(/^\s*<!doctype[^>]*>\s*/i, '');
      return `<!doctype html>\n<html lang="en">\n${headMarkup}\n<body>\n${fragment}\n</body>\n</html>`;
    }

    let normalized = source;
    if (!/^\s*<!doctype/i.test(normalized)) normalized = `<!doctype html>\n${normalized}`;
    if (!/<head\b/i.test(normalized)) {
      normalized = normalized.replace(/<html\b[^>]*>/i, match => `${match}\n${headMarkup}`);
    }
    if (!/<\/head\s*>/i.test(normalized)) {
      normalized = normalized.replace(/<head\b[^>]*>/i, headMarkup);
    }
    if (!/<body\b/i.test(normalized)) {
      normalized = normalized.replace(/<\/head\s*>/i, '</head>\n<body>');
      if (/<\/html\s*>/i.test(normalized)) normalized = normalized.replace(/<\/html\s*>/i, '</body>\n</html>');
      else normalized += '\n</body>';
    }
    return normalized;
  }

  function managedVoiceCssRules(html) {
    const rules = [];
    const matches = html.matchAll(/<style\b(?=[^>]*\bdata-codeup-voice-css\b)[^>]*>([\s\S]*?)<\/style>/gi);
    for (const match of matches) {
      for (const rule of match[1].split('\n').map(line => line.trim()).filter(Boolean)) {
        if (!rules.includes(rule)) rules.push(rule);
      }
    }
    return rules;
  }

  function injectVoiceCss(html, rules) {
    const existing = managedVoiceCssRules(html);
    for (const rule of rules) {
      if (!existing.includes(rule)) existing.push(rule);
    }
    const normalized = normalizeHtmlDocument(html)
      .replace(/\s*<style\b(?=[^>]*\bdata-codeup-voice-css\b)[^>]*>[\s\S]*?<\/style>\s*/gi, '\n');
    const styleBlock = `\n<style data-codeup-voice-css>\n${existing.join('\n')}\n</style>\n`;
    return normalized.replace(/<\/head\s*>/i, `${styleBlock}</head>`);
  }

  function appendCssRules(rules) {
    const cssEl = getCssEditor();
    if (!cssEl) {
      setHtml(injectVoiceCss(getHtml(), rules));
      return;
    }
    const existing = getCss().trim();
    const existingLines = existing.split('\n').map(line => line.trim()).filter(Boolean);
    const nextRules = rules.filter(rule => !existingLines.includes(rule));
    if (!nextRules.length) return;
    setEditorValue(cssEl, existing + (existing ? '\n\n' : '') + nextRules.join('\n'));
    persistDrafts();
    state.pages[state.currentPage] = getHtml();
    scheduleAutosave();
  }

  function noteEditorChanged(editor, draftKey) {
    try { sessionStorage.setItem(draftKey, editorValue(editor)); } catch (error) {}
    state.pages[state.currentPage] = getHtml();
    scheduleAutosave();
  }

  function upgradeTextareaToMonaco(host, editor, editorId, ariaLabel, draftKey) {
    if (!host || !editor || editor.__codeupMonacoEditor || !window.monaco || !window.monaco.editor) return false;
    const monacoHost = document.createElement('div');
    monacoHost.id = editorId + 'Monaco';
    monacoHost.className = 'cu-monaco-editor';
    monacoHost.setAttribute('role', 'region');
    monacoHost.setAttribute('aria-label', ariaLabel + ' Monaco editor');
    host.appendChild(monacoHost);
    try {
      const model = window.monaco.editor.createModel(editor.value || '', MONACO_LANGUAGES[editorId] || 'plaintext');
      const monacoEditor = window.monaco.editor.create(monacoHost, {
        model,
        automaticLayout: true,
        minimap: { enabled: false },
        wordWrap: 'on',
        accessibilitySupport: 'auto',
        tabSize: 2,
        fontFamily: 'JetBrains Mono, Consolas, monospace',
        fontSize: 14,
        lineHeight: 22,
        scrollBeyondLastLine: false,
      });
      if (window.monaco.KeyMod && window.monaco.KeyCode) {
        monacoEditor.addCommand(window.monaco.KeyMod.CtrlCmd | window.monaco.KeyCode.Enter, function () {
          if (editorId === 'pythonEditor') runPythonCode();
          else previewHtml(true);
        });
      }
      editor.__codeupMonacoEditor = monacoEditor;
      editor.__codeupMonacoModel = model;
      editor.dataset.monacoShadow = 'true';
      editor.classList.add('cu-editor-textarea-fallback');
      monacoEditor.onDidChangeModelContent(() => {
        editor.value = monacoEditor.getValue();
        noteEditorChanged(editor, draftKey);
      });
      document.body.dataset.monacoEnabled = 'true';
      const monacoStatus = $('monacoStatusText');
      if (monacoStatus) monacoStatus.textContent = 'active';
      const editorStatus = $('editorModeStatus');
      if (editorStatus) editorStatus.textContent = 'Monaco active';
      return true;
    } catch (error) {
      monacoHost.remove();
      return false;
    }
  }

  function upgradeEditorsWithMonaco() {
    if (!window.monaco || !window.monaco.editor) {
      const monacoStatus = $('monacoStatusText');
      if (monacoStatus) monacoStatus.textContent = 'fallback';
      const editorStatus = $('editorModeStatus');
      if (editorStatus) editorStatus.textContent = 'Textarea fallback';
      return false;
    }
    const upgraded = [
      upgradeTextareaToMonaco($('editor'), getEditor(), 'htmlEditor', 'HTML editor. Type or dictate the page structure.', 'codeup_html_draft'),
      upgradeTextareaToMonaco($('cssEditorHost'), getCssEditor(), 'cssEditor', 'CSS editor. Type or dictate the styles.', 'codeup_css_draft'),
      upgradeTextareaToMonaco($('jsEditorHost'), getJsEditor(), 'jsEditor', 'JavaScript editor. Type or dictate the behaviour.', 'codeup_js_draft'),
      upgradeTextareaToMonaco($('pythonEditorHost'), getPythonEditor(), 'pythonEditor', 'Python editor. Type or dictate a beginner Python program.', 'codeup_python_draft'),
    ].some(Boolean);
    if (upgraded) announce('Monaco editor enabled.');
    return upgraded;
  }

  function makeEditor(hostId, editorId, ariaLabel, draftKey) {
    let editor = $(editorId);
    if (editor) return editor;
    const host = $(hostId);
    if (!host) return null;
    host.innerHTML = '';
    editor = document.createElement('textarea');
    editor.id = editorId;
    editor.className = 'cu-html-editor';
    editor.spellcheck = false;
    editor.setAttribute('aria-label', ariaLabel);
    try { editor.value = sessionStorage.getItem(draftKey) || ''; } catch (error) { editor.value = ''; }
    editor.addEventListener('input', () => {
      noteEditorChanged(editor, draftKey);
    });
    editor.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        if (editorId === 'pythonEditor') runPythonCode();
        else previewHtml(true);
      }
      if (event.key === 'Escape') cancelSpeech();
    });
    host.appendChild(editor);
    return editor;
  }

  function ensureEditors() {
    const htmlEl = makeEditor('editor', 'htmlEditor', 'HTML editor. Type or dictate the page structure.', 'codeup_html_draft');
    const cssEl = makeEditor('cssEditorHost', 'cssEditor', 'CSS editor. Type or dictate the styles.', 'codeup_css_draft');
    const jsEl = makeEditor('jsEditorHost', 'jsEditor', 'JavaScript editor. Type or dictate the behaviour.', 'codeup_js_draft');
    const pythonEl = makeEditor('pythonEditorHost', 'pythonEditor', 'Python editor. Type or dictate a beginner Python program.', 'codeup_python_draft');
    const hasDraft = (htmlEl && htmlEl.value.trim()) || (cssEl && cssEl.value.trim()) || (jsEl && jsEl.value.trim());
    if (!hasDraft) {
      setEditorValue(htmlEl, state.memory.last_html || starterBodyHtml);
      if (cssEl && !state.memory.last_html) setEditorValue(cssEl, starterCss);
      if (jsEl && !state.memory.last_html) setEditorValue(jsEl, starterJs);
      persistDrafts();
    }
    if (pythonEl && !pythonEl.value.trim()) {
      setEditorValue(pythonEl, starterPython);
      try { sessionStorage.setItem('codeup_python_draft', editorValue(pythonEl)); } catch (error) {}
    }
    upgradeEditorsWithMonaco();
    return htmlEl;
  }
  function ensureHtmlEditor() { return ensureEditors(); }

  function replaceButton(id, label, aria, handler, extraClass) {
    const old = $(id);
    if (!old) return null;
    const button = old.cloneNode(false);
    button.id = id;
    button.className = old.className;
    if (extraClass) button.classList.add(extraClass);
    button.textContent = label;
    button.setAttribute('aria-label', aria);
    button.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      cancelSpeech();
      handler();
    });
    old.replaceWith(button);
    return button;
  }

  function ensurePreviewFrame() {
    let frame = $('sitePreviewFrame');
    if (frame) return frame;
    const wrapper = $('sitePreview') || document.querySelector('.cu-output-wrapper');
    if (!wrapper) return null;
    const preview = wrapper.id === 'sitePreview' ? wrapper : document.createElement('section');
    preview.classList.add('cu-site-preview');
    preview.setAttribute('aria-label', 'Local website preview');
    preview.innerHTML = [
      '<div class="cu-panel-title">LOCAL WEBSITE PREVIEW</div>',
      '<div class="cu-preview-toolbar" role="toolbar" aria-label="Preview controls">',
      '  <button id="previewDesktopBtn" class="cu-button" type="button" aria-pressed="true">Desktop</button>',
      '  <button id="previewTabletBtn" class="cu-button" type="button" aria-pressed="false">Tablet</button>',
      '  <button id="previewMobileBtn" class="cu-button" type="button" aria-pressed="false">Mobile</button>',
      '  <button id="previewRefreshBtn" class="cu-button" type="button">Reload</button>',
      '  <button id="previewDescribeBtn" class="cu-button" type="button">Describe</button>',
      '  <button id="sitePreviewOpenBtn" class="cu-button cu-button-secondary" type="button" disabled>Open local site</button>',
      '</div>',
      '<div id="previewEmpty" class="ide-preview-empty">',
      '  <p class="ide-preview-empty-title">Your website preview will appear here.</p>',
      '  <p class="ide-preview-empty-hint">Try',
      '    <button type="button" class="ide-chip" data-cmd="make a portfolio website">make a portfolio website</button>',
      '    or',
      '    <button type="button" class="ide-chip" data-cmd="make a quiz app about Python basics">make a quiz app about Python basics</button>.',
      '  </p>',
      '</div>',
      '<iframe id="sitePreviewFrame" title="Student website preview" sandbox="allow-scripts allow-forms allow-modals"></iframe>',
    ].join('');
    if (preview !== wrapper) wrapper.appendChild(preview);
    const openBtn = $('sitePreviewOpenBtn');
    if (openBtn && !openBtn.dataset.bound) {
      openBtn.dataset.bound = 'true';
      openBtn.addEventListener('click', () => {
        const currentFrame = $('sitePreviewFrame');
        const url = state.lastUrl || ((currentFrame?.getAttribute('src') || '').split('?')[0]);
        if (url) window.open(url, '_blank', 'noopener');
      });
    }
    bindPreviewToolbar();
    return $('sitePreviewFrame');
  }

  function setPreviewViewport(mode, shouldSpeak = true) {
    const preview = $('sitePreview');
    const frame = ensurePreviewFrame();
    if (!preview || !frame) return false;
    const next = ['mobile', 'tablet', 'desktop'].includes(mode) ? mode : 'desktop';
    preview.dataset.viewport = next;
    [['previewDesktopBtn', 'desktop'], ['previewTabletBtn', 'tablet'], ['previewMobileBtn', 'mobile']].forEach(([id, value]) => {
      const button = $(id);
      if (button) button.setAttribute('aria-pressed', value === next ? 'true' : 'false');
    });
    const label = next.charAt(0).toUpperCase() + next.slice(1);
    announce(`Preview viewport: ${label}.`);
    if (shouldSpeak) writeOutput(`Preview switched to ${label} width.`, true);
    return true;
  }

  function bindPreviewToolbar() {
    const bindings = [
      ['previewDesktopBtn', () => setPreviewViewport('desktop')],
      ['previewTabletBtn', () => setPreviewViewport('tablet')],
      ['previewMobileBtn', () => setPreviewViewport('mobile')],
      ['previewRefreshBtn', () => previewHtml(true)],
      ['previewDescribeBtn', () => describePreview()],
    ];
    bindings.forEach(([id, handler]) => {
      const button = $(id);
      if (button && !button.dataset.bound) {
        button.dataset.bound = 'true';
        button.addEventListener('click', handler);
      }
    });
  }
  function markPreviewReady() {
    const preview = $('sitePreview');
    if (preview) preview.classList.add('has-preview');
    const previewStatus = $('previewStatusText');
    if (previewStatus) previewStatus.textContent = 'live';
  }

  async function saveMemory(payload) {
    try {
      const response = await fetch('/html-memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (data.success && data.memory) {
        state.memory = data.memory;
        state.lastReview = data.memory.last_review || state.lastReview;
      }
    } catch (error) {}
  }

  async function loadMemory() {
    try {
      const response = await fetch('/html-memory');
      const data = await response.json();
      if (data.success && data.memory) {
        state.memory = data.memory;
        state.lastReview = data.memory.last_review || '';
      }
    } catch (error) {}
  }

  async function publish(html) {
    state.pages[state.currentPage] = html;
    const pages = activePages();
    const payload = Object.keys(pages).length > 1 ? { html, pages } : { html };
    if (state.projectId) payload.project_id = state.projectId;
    payload.current_page = state.currentPage;
    const response = await fetch('/publish-site', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || 'Could not publish website.');
    state.lastUrl = data.url;
    state.memory.last_url = data.url;
    const frame = ensurePreviewFrame();
    if (frame) frame.src = data.url + '?t=' + Date.now();
    markPreviewReady();
    const openBtn = $('sitePreviewOpenBtn');
    if (openBtn) {
      openBtn.disabled = false;
      openBtn.dataset.url = data.url;
    }
    if (data.warnings && data.warnings.length) {
      const warningText = 'Preview note: ' + data.warnings.join('; ') + '. Only inline scripts and styles are supported in the hosted preview.';
      announce(warningText);
      const output = $('output');
      if (output) output.textContent = warningText + '\n' + (output.textContent || '');
    }
    await saveMemory({ html, url: data.url, note: 'Published local preview' });
    return data.url;
  }

  function applyPageLinks(html) {
    if (!Object.keys(state.pages).length) return html;
    return html
      .replace(/href="#home"/gi, 'href="index.html"')
      .replace(/href="#about"/gi, 'href="about.html"')
      .replace(/href="#contact"/gi, 'href="contact.html"');
  }

  function htmlOutline(html) {
    const matches = [...html.matchAll(/<h([1-6])\b[^>]*>(.*?)<\/h\1>/gi)];
    if (!matches.length) return t('No headings found yet. Add an h1 and section headings.', 'Abhi headings nahi mili. H1 aur section headings add karein.');
    return matches.map((match) => {
      const level = Number(match[1]);
      const text = match[2].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
      return `${'  '.repeat(Math.max(0, level - 1))}H${level}: ${text}`;
    }).join('\n');
  }

  function makeTemplateHtml(kind) {
    const template = pageTemplates[kind] || pageTemplates['club page'];
    const slug = slugify(template.title);
    return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${template.title}</title>
  <style>
    body { margin: 0; font-family: Arial, sans-serif; color: #182620; background: #fbf7ed; line-height: 1.6; }
    header { padding: 48px 20px; color: white; background: #0f766e; text-align: center; }
    nav a { color: white; margin: 0 8px; font-weight: 700; }
    main { max-width: 920px; margin: 0 auto; padding: 24px 18px 44px; }
    section { margin: 18px 0; padding: 22px; border: 1px solid #d9e2dc; border-radius: 8px; background: white; }
  </style>
</head>
<body>
  <header>
    <h1>${template.title}</h1>
    <p>Customize this ${kind} template with your own details.</p>
    <nav aria-label="Site pages"><a href="index.html">Home</a><a href="about.html">About</a><a href="contact.html">Contact</a></nav>
  </header>
  <main id="${slug}-main">
    ${template.sections.map((section, index) => `<section aria-labelledby="section-${index + 1}"><h2 id="section-${index + 1}">${section}</h2><p>Add clear details for ${section.toLowerCase()} here.</p></section>`).join('\n    ')}
    <section id="contact" aria-labelledby="contact-heading"><h2 id="contact-heading">Contact</h2><p>Add a teacher, club leader, or team email here.</p></section>
  </main>
</body>
</html>`;
  }

  function createMultiPageSite(topic) {
    const title = topic ? topic.replace(/\b(homepage|about page|contact page|website|site)\b/gi, '').trim() : 'Student Website';
    const base = title || 'Student Website';
    state.pages = {
      home: makeTemplateHtml('school event').replace(/School Event/g, base),
      about: makeTemplateHtml('personal portfolio').replace(/Personal Portfolio/g, `${base} About`),
      contact: makeTemplateHtml('charity drive').replace(/Charity Drive/g, `${base} Contact`),
    };
    state.currentPage = 'home';
    Object.keys(state.pages).forEach((key) => { state.pages[key] = applyPageLinks(state.pages[key]); });
    setHtml(state.pages.home);
    snapshotVersion('Created multi-page website');
    writeOutput('Created a homepage, about page, and contact page. You are editing the homepage.', true);
  }

  function switchPage(pageName) {
    const page = slugify(pageName || '').replace(/-/g, ' ');
    const key = page.includes('about') ? 'about' : page.includes('contact') ? 'contact' : 'home';
    state.pages[state.currentPage] = getHtml();
    if (!state.pages[key]) state.pages[key] = makeTemplateHtml('club page').replace(/Club Page/g, key.charAt(0).toUpperCase() + key.slice(1));
    state.currentPage = key;
    setHtml(state.pages[key]);
    writeOutput(`Now editing ${key} page.`, true);
  }

  function useTemplate(kind) {
    const lower = kind.toLowerCase();
    const name = Object.keys(pageTemplates).find(item => lower.includes(item)) || 'club page';
    state.currentPage = 'home';
    state.pages = {};
    setHtml(makeTemplateHtml(name));
    snapshotVersion(`Started from ${name} template`);
    writeOutput(`Loaded ${name} template.`, true);
  }

  function projectPayload(extra = {}) {
    return Object.assign({
      html: getHtmlSource(),
      css: getCss(),
      js: getJs(),
      name: state.projectName,
      project_name: state.projectName,
      project_type: state.projectType || 'generic_website',
      audit: state.lastAudit || null,
    }, extra);
  }

  async function exportHtml() {
    const token = startHeartbeat('Exporting project');
    const fileExport = {
      'index.html': ensureManagedRefs(stripManagedBlocks(normalizeHtmlDocument(getHtmlSource())), !!getCss().trim(), !!getJs().trim()),
      'style.css': getCss(),
      'script.js': getJs(),
    };
    try {
      const response = await fetch('/export-site.zip', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: state.projectId,
          files: fileExport,
          name: state.projectName,
          project_type: state.projectType || 'generic_website',
          audit: state.lastAudit || null,
          code_map: state.lastCodeMap,
          step_narration: state.lastStepNarration,
          learning_notes: state.lastLearningNotes,
          accessibility_map: state.lastAccessibilityMap,
          project_review: state.lastProjectReview,
          preview_description: state.lastPreviewDescription,
          project_summary: state.lastProjectSummary,
          trainer_notes: state.lastTrainerNotes,
          student_recap: state.lastStudentRecap,
          screen_reader_summary: state.lastScreenReaderSummary,
          run_summary: state.lastRunSummary,
          debug_report: state.lastDebugReport,
          screen_reader_tour: state.lastScreenReaderTour,
          keyboard_test: state.lastKeyboardTest,
          visual_description: state.lastVisualDescription,
          readiness_score: state.lastReadinessScore,
          teacher_review: state.lastTeacherReview,
          pilot_report: state.lastPilotReport,
          commands: (state.commandHistory || []).slice(-20),
          change_replay: exportChangeReplay(),
          bookmarks: loadJsonStore('codeup_bookmarks', {}),
          versions: (state.versions || []).slice(-10).map((v) => ({
            label: v.note || v.label, command: v.command || '', summary: v.summary || [], timestamp: v.timestamp || '',
          })),
        }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || 'ZIP export failed.');
      }
      const blob = await response.blob();
      if (!isAsyncFresh(token)) return;
      const link = document.createElement('a');
      const objectUrl = URL.createObjectURL(blob);
      link.href = objectUrl;
      link.download = slugify(state.projectName || 'codeup-site') + '.zip';
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 500);
      state.exportStatus = 'exported';
      writeOutput(t(
        'Done! Your ZIP includes index.html, style.css, script.js, README.txt, and learning notes: CODE_MAP.txt, STEP_NARRATION.txt, LEARNING_NOTES.txt, PROJECT_SUMMARY.txt, PROJECT_REVIEW.txt, PREVIEW_DESCRIPTION.txt, TRAINER_NOTES.txt, STUDENT_RECAP.txt, and SCREEN_READER_SUMMARY.txt. Open index.html to view your site.',
        'Ho gaya! Aapke ZIP mein index.html, style.css, script.js, README.txt, aur learning notes hain: CODE_MAP.txt, STEP_NARRATION.txt, LEARNING_NOTES.txt, PROJECT_SUMMARY.txt, PROJECT_REVIEW.txt, PREVIEW_DESCRIPTION.txt, TRAINER_NOTES.txt, STUDENT_RECAP.txt, aur SCREEN_READER_SUMMARY.txt. Site dekhne ke liye index.html kholiye.'
      ), true);
      stopHeartbeat(token);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      state.exportStatus = 'failed';
      stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  function previewDocument() {
    const parser = new DOMParser();
    return parser.parseFromString(getHtml(), 'text/html');
  }

  function rebuildNavigator() {
    const doc = previewDocument();
    const selectors = 'h1,h2,h3,h4,h5,h6,section,article,nav,main,p,button,a,img,form,label,input,textarea,select';
    state.navigator.items = [...doc.body.querySelectorAll(selectors)].map((node, index) => {
      const tag = node.tagName.toLowerCase();
      const text = (node.getAttribute('alt') || node.getAttribute('aria-label') || node.textContent || node.getAttribute('placeholder') || '').replace(/\s+/g, ' ').trim();
      return { tag, text: text || `${tag} ${index + 1}`, index };
    });
    if (state.navigator.index >= state.navigator.items.length) state.navigator.index = state.navigator.items.length - 1;
  }

  function readNavigatorItem(item) {
    if (!item) {
      speak('No matching page element found.');
      return;
    }
    const label = `${item.tag} ${item.index + 1}: ${item.text}`;
    writeOutput(label, true);
  }

  function navigatePreview(command) {
    rebuildNavigator();
    const lower = command.toLowerCase();
    if (!state.navigator.items.length) {
      speak('No readable elements found in the current HTML.');
      return true;
    }
    if (lower.includes('previous')) state.navigator.index = Math.max(0, state.navigator.index - 1);
    else if (lower.includes('next')) state.navigator.index = Math.min(state.navigator.items.length - 1, state.navigator.index + 1);
    const paragraph = lower.match(/paragraph\s+(\d+)/);
    if (paragraph) {
      const paragraphs = state.navigator.items.filter(item => item.tag === 'p');
      readNavigatorItem(paragraphs[Number(paragraph[1]) - 1]);
      return true;
    }
    const tag = lower.includes('heading') ? /^h[1-6]$/ : lower.includes('section') ? /^section$/ : null;
    if (tag) {
      const direction = lower.includes('previous') ? -1 : 1;
      let cursor = state.navigator.index;
      for (let i = 0; i < state.navigator.items.length; i += 1) {
        cursor = Math.max(0, Math.min(state.navigator.items.length - 1, cursor + direction));
        if (tag.test(state.navigator.items[cursor].tag)) {
          state.navigator.index = cursor;
          break;
        }
      }
    }
    readNavigatorItem(state.navigator.items[state.navigator.index]);
    return true;
  }

  function applyCssEdit(command) {
    const lower = command.toLowerCase();
    const colors = {
      cream: '#fbf3df',
      white: '#ffffff',
      black: '#111827',
      dark: '#111827',
      navy: '#1e3a8a',
      blue: '#2563eb',
      teal: '#0f766e',
      green: '#15803d',
      yellow: '#facc15',
      orange: '#f97316',
      red: '#dc2626',
      pink: '#db2777',
      purple: '#7c3aed',
      gray: '#6b7280',
      grey: '#6b7280',
    };
    const findColor = () => {
      const hex = lower.match(/#[0-9a-f]{3,6}\b/i);
      if (hex) return hex[0];
      return Object.keys(colors).find(name => lower.includes(name)) ? colors[Object.keys(colors).find(name => lower.includes(name))] : '';
    };
    const size = (fallback, min = 12, max = 96) => {
      const match = lower.match(/(\d{1,3})\s*(px|pixel|pixels|rem|em|percent|%)/);
      if (!match) return fallback;
      const amount = Math.max(min, Math.min(max, Number(match[1])));
      if (match[2].startsWith('percent') || match[2] === '%') return `${amount}%`;
      if (match[2] === 'rem' || match[2] === 'em') return `${Math.max(0.5, Math.min(6, amount))}${match[2]}`;
      return `${amount}px`;
    };
    const selector = lower.includes('button') ? 'button, .button, a.button'
      : lower.includes('paragraph') || lower.includes('body text') ? 'p'
      : lower.includes('section') || lower.includes('card') ? 'section, article, .card'
      : lower.includes('link') ? 'a'
      : lower.includes('heading') || lower.includes('title') ? 'h1, h2, h3'
      : 'body';
    const rules = [];
    let color = findColor();
    if (!color && lower.includes('background') && lower.includes('color')) color = '#eef6ff';
    if (color && lower.includes('background')) rules.push(`${selector === 'body' ? 'body' : selector} { background: ${color}; }`);
    if (color && (lower.includes('text') || lower.includes('font color') || lower.includes('words'))) rules.push(`${selector} { color: ${color}; }`);
    if (color && lower.includes('button')) rules.push(`button, .button, a.button { background: ${color}; }`);
    if ((lower.includes('bigger') || lower.includes('larger') || lower.includes('increase')) && (lower.includes('heading') || lower.includes('text') || lower.includes('font'))) {
      rules.push(`${selector} { font-size: ${size(selector.includes('h1') ? 'clamp(2rem, 6vw, 4rem)' : '1.15rem')}; }`);
    }
    if ((lower.includes('smaller') || lower.includes('decrease') || lower.includes('reduce')) && (lower.includes('heading') || lower.includes('text') || lower.includes('font'))) {
      rules.push(`${selector} { font-size: ${size(selector.includes('h1') ? '1.6rem' : '0.95rem')}; }`);
    }
    if (lower.includes('center')) rules.push(`${selector} { text-align: center; }`);
    if (lower.includes('left align') || lower.includes('align left')) rules.push(`${selector} { text-align: left; }`);
    if (lower.includes('bold')) rules.push(`${selector} { font-weight: 700; }`);
    if (lower.includes('rounded')) rules.push(`${selector} { border-radius: ${size('12px', 0, 40)}; }`);
    if (lower.includes('more spacing') || lower.includes('more space') || lower.includes('spread out')) rules.push('section, article, .card { margin-block: 28px; padding: 30px; } main { padding-block: 40px; }');
    if (lower.includes('less spacing') || lower.includes('less space') || lower.includes('closer together')) rules.push('section, article, .card { margin-block: 12px; padding: 16px; } main { padding-block: 20px; }');
    if (lower.includes('high contrast')) rules.push('body { color: #0f172a; background: #ffffff; } a, button, .button { color: #ffffff; background: #0f172a; }');
    if (!rules.length) return false;
    snapshotVersion('Before CSS voice edit');
    beginReplay('Before CSS edit');
    appendCssRules(rules);
    finishReplay('After CSS edit');
    writeOutput(`Applied CSS edit: ${rules.join(' ')}`, true);
    previewHtml(false, { silent: true });
    return true;
  }

  function contrastRatio(fg, bg) {
    const parse = (hex) => {
      const value = hex.replace('#', '');
      const full = value.length === 3 ? value.split('').map(char => char + char).join('') : value;
      const rgb = [0, 2, 4].map(i => parseInt(full.slice(i, i + 2), 16) / 255).map(v => v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
      return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
    };
    const a = parse(fg);
    const b = parse(bg);
    return ((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toFixed(2);
  }

  function announceContrast() {
    const html = getHtml();
    const fg = (html.match(/(?:color|--ink)\s*:\s*(#[0-9a-f]{3,6})/i) || [])[1] || '#17202a';
    const bg = (html.match(/(?:background|--paper)\s*:\s*(#[0-9a-f]{3,6})/i) || [])[1] || '#ffffff';
    const ratio = contrastRatio(fg, bg);
    writeOutput(`Estimated main text contrast is ${ratio} to 1 for ${fg} on ${bg}. WCAG AA needs 4.5 to 1 for normal text.`, true);
  }

  function explainConcept(command) {
    const concepts = {
      div: 'A div is a generic container. Use it for grouping when no semantic element like header, main, section, nav, or button fits.',
      'aria-label': 'aria-label gives an accessible name to an element when visible text is missing or not enough, such as an icon-only button.',
      section: 'A section groups related content and usually needs a heading so screen reader users can understand the page outline.',
      heading: 'Headings name each part of a page. Screen reader users often jump by headings to skim the structure.',
      contrast: 'Color contrast compares text color against its background. A higher ratio makes text easier to read for sighted visitors.',
    };
    const key = Object.keys(concepts).find(item => command.toLowerCase().includes(item));
    if (!key) return false;
    speak(concepts[key]);
    writeOutput(concepts[key], false);
    return true;
  }

  async function undoByVoice(command) {
    const match = command.toLowerCase().match(/(?:back|undo)\s+(\d+)/);
    const words = { one: 1, two: 2, three: 3, four: 4, five: 5 };
    const wordMatch = command.toLowerCase().match(/(?:back|undo)\s+(one|two|three|four|five)/);
    const steps = match ? Number(match[1]) : wordMatch ? words[wordMatch[1]] : 1;
    if (state.versions.length <= 1) {
      speak('No earlier version is available.');
      return true;
    }
    const target = Math.max(0, state.versions.length - 1 - steps);
    const version = state.versions[target];
    if (version.id && await restoreVersionFromServer(version.id)) {
      writeOutput(`Restored version: ${version.note || version.label}.`, true);
      return true;
    }
    state.versions = state.versions.slice(0, target + 1);
    persistVersions();
    setHtml(version.html);
    writeOutput(`Restored version: ${version.note}.`, true);
    return true;
  }

  async function reviewChanges() {
    await narrateReplay('what changed');
    return true;
  }

  function _htmlWords(html) {
    const text = html.replace(/<[^>]+>/g, ' ').toLowerCase().match(/[a-z][a-z0-9-]{3,}/g) || [];
    return new Set(text);
  }

  async function resetSession() {
    cancelSpeech();
    try {
      await fetch('/reset-session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: state.lastUrl || state.memory.last_url || '' }),
      });
    } catch (error) {}
    state.memory = { history: [], last_html: '', last_url: '', last_review: '' };
    state.lastReview = '';
    state.lastUrl = '';
    state.pages = {};
    state.currentPage = 'home';
    state.projectId = '';
    state.projectName = 'Untitled Project';
    state.projectType = 'generic_website';
    state.lastCodeMap = '';
    state.lastStepNarration = '';
    state.lastLearningNotes = '';
    state.lastAccessibilityMap = '';
    state.lastFileExplanation = '';
    state.lastProjectReview = '';
    state.lastPreviewDescription = '';
    state.lastProjectSummary = '';
    try {
      sessionStorage.removeItem('codeup_html_draft');
      sessionStorage.removeItem('codeup_css_draft');
      sessionStorage.removeItem('codeup_js_draft');
    } catch (error) {}
    loadGeneratedFiles(starterFiles);
    activateTab('html');
    try {
      const data = await apiJson('/projects', {
        method: 'POST',
        body: JSON.stringify({ name: state.projectName, html: getHtml(), current_page: state.currentPage }),
      });
      state.projectId = data.project.id;
      state.projectName = data.project.name;
      await refreshProjectList();
    } catch (error) {}
    const frame = $('sitePreviewFrame');
    if (frame) frame.removeAttribute('src');
    const openBtn = $('sitePreviewOpenBtn');
    if (openBtn) {
      openBtn.disabled = true;
      delete openBtn.dataset.url;
    }
    writeOutput(t('Session reset. Starter website loaded.', 'Session reset ho gaya. Starter website load ho gayi.'), true);
  }

  async function auditWebsite(shouldSpeak = true) {
    writeOutput(t('Auditing accessibility...', 'Accessibility audit chal raha hai...'), shouldSpeak);
    const token = startHeartbeat('Auditing accessibility');
    try {
      const response = await fetch('/html-audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html: getHtml(), project_id: state.projectId }),
      });
      const data = await response.json();
      if (!data.success) throw new Error(data.error || 'Audit failed.');
      const audit = data.audit;
      state.lastAudit = audit;
      const checks = audit.checks.map(item => `${item.passed ? 'PASS' : 'FIX'} - ${item.label}`).join('\n');
      const issues = (audit.issues || []).map(item => `${item.severity.toUpperCase()} - ${item.id}: ${item.description}\n  Why it matters: ${item.why_matters || 'This can make the website harder to use.'}\n  Fix: ${item.suggested_fix}`).join('\n');
      const suggestions = audit.suggestions.map(item => `- ${item}`).join('\n');
      const contrast = (audit.contrast_pairs || []).map(item => `${item.passes_aa ? 'PASS' : 'FIX'} - ${item.selector}: ${item.ratio}:1`).join('\n');
      const transcript = (audit.screen_reader_transcript || []).slice(0, 12).map(item => `- ${item.announcement}`).join('\n');
      const message = `Accessibility score: ${audit.score}/100\n\n${checks}\n\nIssues:\n${issues || 'No structured issues found.'}\n\nContrast:\n${contrast || 'No color pairs found.'}\n\nScreen reader transcript preview:\n${transcript || 'No readable announcements found.'}\n\nSuggestions:\n${suggestions}`;
      const one = $('auditFixOneBtn');
      const all = $('auditFixAllBtn');
      const fixable = (audit.issues || []).filter(item => item.autofix);
      if (one) one.disabled = fixable.length === 0;
      if (all) all.disabled = fixable.length === 0;
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(message, shouldSpeak);
      const issueCount = (audit.issues || []).length;
      suggestNext(issueCount ? ['fix accessibility issues', 'accessibility map'] : ['describe preview', 'export website']);
      await checkWatchpoints('Audit');
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  async function applyAuditFix(issueId, shouldSpeak = true) {
    const html = getHtml();
    writeOutput(issueId ? `Applying fix ${issueId}...` : 'Applying safe audit fixes...', shouldSpeak);
    beginReplay('Before accessibility fix');
    const token = startHeartbeat('Fixing accessibility');
    try {
      const response = await fetch('/audit-autofix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          html,
          project_id: state.projectId,
          current_page: state.currentPage,
          issue_id: issueId || '',
          fix_all: !issueId,
        }),
      });
      const data = await response.json();
      if (!data.success) throw new Error(data.error || 'Audit autofix failed.');
      if (!isAsyncFresh(token)) return;
      snapshotVersion('Before audit autofix');
      setHtml(data.code);
      snapshotVersion('Applied audit autofix', data.summary || []);
      state.lastAudit = data.audit;
      const fixableRemaining = (data.audit.issues || []).filter(item => item.autofix);
      const one = $('auditFixOneBtn');
      const all = $('auditFixAllBtn');
      if (one) one.disabled = fixableRemaining.length === 0;
      if (all) all.disabled = fixableRemaining.length === 0;
      await publish(data.code);
      finishReplay('After accessibility fix');
      stopHeartbeat(token);
      const fixed = (data.fixed || []).join(', ') || 'nothing';
      writeOutput(`Applied safe audit fixes: ${fixed}.\n${(data.summary || []).join('\n')}`, shouldSpeak);
      await checkWatchpoints('Accessibility fix');
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  async function applyFirstAuditFix() {
    const issue = ((state.lastAudit || {}).issues || []).find(item => item.autofix);
    if (!issue) {
      writeOutput('No safe autofix is available. Run Audit first.', true);
      return;
    }
    await applyAuditFix(issue.id, true);
  }

  async function applyAllAuditFixes() {
    await applyAuditFix('', true);
  }

  async function createNamedProject() {
    const requested = (($('projectNameInput') || {}).value || 'Untitled Project').trim() || 'Untitled Project';
    try {
      const data = await apiJson('/projects', {
        method: 'POST',
        body: JSON.stringify({ name: requested, pages: activePages(), current_page: state.currentPage }),
      });
      state.projectId = data.project.id;
      state.projectName = data.project.name;
      await refreshProjectList();
      updateProjectUi();
      writeOutput(`Created project: ${state.projectName}.`, true);
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  async function renameProject() {
    if (!state.projectId) {
      await createNamedProject();
      return;
    }
    const requested = (($('projectNameInput') || {}).value || state.projectName).trim() || state.projectName;
    try {
      const data = await apiJson(`/projects/${encodeURIComponent(state.projectId)}`, {
        method: 'PATCH',
        body: JSON.stringify({ name: requested, pages: activePages(), current_page: state.currentPage }),
      });
      state.projectName = data.project.name;
      await refreshProjectList();
      writeOutput(`Saved project: ${state.projectName}.`, true);
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  async function duplicateCurrentProject() {
    if (!state.projectId) {
      await createNamedProject();
      return;
    }
    try {
      await saveProjectDraft();
      const data = await apiJson(`/projects/${encodeURIComponent(state.projectId)}/duplicate`, {
        method: 'POST',
        body: JSON.stringify({ name: `${state.projectName} Copy` }),
      });
      await refreshProjectList();
      await openProject(data.project.id);
      writeOutput(`Duplicated project: ${data.project.name}.`, true);
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  async function openSelectedProject() {
    const selected = ($('projectSelect') || {}).value;
    if (!selected) return;
    try {
      await openProject(selected);
      await previewHtml(false, { silent: true });
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  function outlineWebsite(shouldSpeak = true) {
    const message = t('Website outline:\n', 'Website outline:\n') + htmlOutline(getHtml());
    writeOutput(message, shouldSpeak);
  }

  function toggleDemoMode() {
    state.demoMode = !state.demoMode;
    document.body.classList.toggle('cu-demo-mode', state.demoMode);
    const button = $('demoModeBtn');
    if (button) {
      button.setAttribute('aria-pressed', state.demoMode ? 'true' : 'false');
      button.textContent = state.demoMode ? 'Demo On' : 'Demo Mode';
    }
    speak(t(
      state.demoMode ? 'Demo mode on. The interface is larger and calmer.' : 'Demo mode off.',
      state.demoMode ? 'Demo mode on hai. Interface bada aur clear hai.' : 'Demo mode off hai.'
    ));
  }

  async function previewHtml(shouldSpeak = false, options = {}) {
    const html = getHtml();
    const silent = !!options.silent;
    const token = silent ? nextAsyncToken() : startHeartbeat('Publishing preview');
    if (!silent) writeOutput(t('Publishing local preview...', 'Website local preview mein publish ho rahi hai...'));
    try {
      const url = await publish(html);
      if (!isAsyncFresh(token)) return;
      const message = t(
        `Website is live locally at ${url}\nThe HTML is in the editor and the preview is below.`,
        `Website ready hai: ${url}\nHTML editor mein hai aur preview neeche dikh raha hai.`
      );
      if (!silent) writeOutput(message, shouldSpeak);
      announce('Website preview ready');
      if (!silent) stopHeartbeat(token);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      if (!silent) stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  async function explainWebsite(shouldSpeak = true) {
    const html = getHtml();
    writeOutput(t('Explaining website...', 'Website explain ho rahi hai...'));
    try {
      const response = await fetch('/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: html, language: lang() }),
      });
      const data = await response.json();
      const explanation = data.analysis || t('No explanation available.', 'Explanation available nahi hai.');
      writeOutput(explanation, shouldSpeak);
      await saveMemory({ html, note: 'Explained website' });
    } catch (error) {
      writeOutput(t('Explanation failed.', 'Explanation fail ho gayi.'), true);
    }
  }

  async function reviewWebsite(shouldSpeak = true) {
    const html = getHtml();
    writeOutput(t('Reviewing website like a sighted guide...', 'Website ko sighted guide ki tarah review kar raha hoon...'), shouldSpeak);
    try {
      const response = await fetch('/review-site', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html, language: lang() }),
      });
      const data = await response.json();
      if (!data.success) throw new Error(data.error || 'Review failed.');
      if (data.memory) state.memory = data.memory;
      state.lastReview = data.review || '';
      writeOutput(state.lastReview, shouldSpeak);
      return state.lastReview;
    } catch (error) {
      writeOutput(error.message, true);
      return '';
    }
  }

  async function applyReviewSuggestion(instruction, shouldSpeak = true) {
    const html = getHtml();
    const review = state.lastReview || state.memory.last_review || '';
    writeOutput(t('Applying the review suggestions...', 'Review suggestions apply ho rahe hain...'), shouldSpeak);
    try {
      const response = await fetch('/apply-review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          html,
          instruction: instruction || 'Apply the latest review suggestions',
          review,
          language: lang(),
          project_id: state.projectId,
        }),
      });
      const data = await response.json();
      if (!data.success || !data.code) throw new Error(data.error || 'Could not apply review suggestions.');
      snapshotVersion('Before applying review');
      setHtml(data.code);
      snapshotVersion('Applied review suggestions', data.summary || []);
      if (data.memory) state.memory = data.memory;
      const url = await publish(data.code);
      const nextReview = await reviewWebsite(false);
      const message = t(
        `I added the review improvements, republished the website at ${url}, and reviewed the new version.\nChanges: ${(data.summary || []).join(' ')}\n${nextReview}`,
        `Review improvements add ho gaye, website ${url} par republish ho gayi.\nChanges: ${(data.summary || []).join(' ')}\n${nextReview}`
      );
      if (shouldSpeak) speak(message);
    } catch (error) {
      writeOutput(error.message, true);
    }
  }
  async function buildWebsite(prompt, shouldSpeak = true, options = {}) {
    cancelSpeech();
    if (!prompt) {
      writeOutput(t(
        'Type or say a request like: generate a website for my robotics lab.',
        'Request boliye ya likhiye: mere robotics lab ke liye website banao.'
      ), true);
      return;
    }
    const isEdit = !!options.edit;
    const normalized = isEdit || /^(build|make|create|generate)/i.test(prompt)
      ? prompt
      : 'Build a website for ' + prompt;

    writeOutput(t(
      isEdit ? 'Editing the current website...' : 'Generating HTML, CSS, and JavaScript...',
      isEdit ? 'Current website edit ho rahi hai...' : 'HTML, CSS aur JavaScript ban rahe hain...'
    ));
    updateStateIndicator('PROCESSING');
    beginReplay(isEdit ? 'Before website edit' : 'Before website generation');
    const token = startHeartbeat(isEdit ? 'Editing website' : 'Generating website');
    try {
      const data = await apiJson('/generate-site', {
        method: 'POST',
        body: JSON.stringify({
          prompt: normalized,
          html: getHtmlSource(),
          css: getCss(),
          js: getJs(),
          edit: isEdit,
          language: lang(),
          project_id: state.projectId,
          previous_generation_request: state.originalGenerationRequest,
          metadata: {
            project_name: state.projectName,
            current_page: state.currentPage,
            last_edit_request: state.lastEditRequest,
            last_edit_summary: state.lastEditSummary,
            last_accessibility_audit: state.lastAudit,
            export_status: state.exportStatus,
          },
        }),
      });
      if (!data.html) throw new Error(data.error || 'Website generation failed.');
      if (!isAsyncFresh(token)) return;
      snapshotVersion(isEdit ? 'Before editing website' : 'Before generating website');
      if (!isEdit) { state.currentPage = 'home'; state.pages = {}; }
      loadGeneratedFiles({ html: data.html, css: data.css, js: data.js });
      state.projectType = data.project_type || state.projectType || 'generic_website';
      state.lastCodeMap = '';
      state.lastStepNarration = '';
      state.lastLearningNotes = '';
      state.lastAccessibilityMap = '';
      state.lastFileExplanation = '';
      state.lastProjectReview = '';
      state.lastPreviewDescription = '';
      state.lastProjectSummary = '';
      if (isEdit) {
        state.lastEditRequest = prompt;
        state.lastEditSummary = (data.summary || []).join(' ');
      } else {
        state.originalGenerationRequest = normalized;
      }
      finishReplay(isEdit ? 'After website edit' : 'After website generation');
      snapshotVersion(isEdit ? 'Edited website' : 'Generated website');
      activateTab('html');
      let url = '';
      try { url = await publish(getHtml()); } catch (error) {}
      await saveMemory({ prompt: normalized, html: getHtml(), url });
      const summary = (data.summary || []).join(' ');
      const message = t(
        isEdit
          ? `Done. I updated the existing website and refreshed the live preview. ${summary}`
          : `Done. I created separate index.html, style.css, and script.js files and updated the live preview. ${summary}`,
        isEdit
          ? `Ho gaya. Existing website update ho gayi aur preview refresh ho gaya. ${summary}`
          : `Ho gaya. Alag index.html, style.css aur script.js files ban gayi aur preview update ho gaya. ${summary}`
      );
      writeOutput(message, shouldSpeak);
      suggestNext(isEdit
        ? ['replay change', 'check accessibility', 'describe preview']
        : ['code map', 'add a section about competitions', 'check accessibility']);
      updateStateIndicator('IDLE');
      stopHeartbeat(token);
      await checkWatchpoints('Generation');
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      updateStateIndicator('IDLE');
      stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  async function polishHtml() {
    writeOutput(t('Polishing HTML...', 'HTML polish ho raha hai...'), true);
    try {
      const response = await fetch('/fix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: getHtml(), language: lang(), project_id: state.projectId }),
      });
      const data = await response.json();
      if (!data.success || !data.code) throw new Error(data.error || 'Could not polish the HTML.');
      snapshotVersion('Before polishing HTML');
      setHtml(data.code);
      snapshotVersion('Polished HTML', data.summary || []);
      await publish(data.code);
      writeOutput(t(
        `HTML polished and preview updated.\nChanges: ${(data.summary || []).join(' ')}`,
        `HTML polish ho gaya aur preview update ho gaya.\nChanges: ${(data.summary || []).join(' ')}`
      ), true);
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  async function chatWithAI(message, shouldSpeak = true) {
    cancelSpeech();
    if (!message) {
      speak(t(
        'Ask me anything about this tool or your website.',
        'Aap is tool ya apni website ke baare mein kuch bhi pooch sakte hain.'
      ));
      return;
    }
    if (window.VoiceMemoryEngine && shouldSpeak) {
      writeOutput(t('Thinking...', 'Soch raha hoon...'));
      updateStateIndicator('PROCESSING');
      const reply = await window.VoiceMemoryEngine.chatWithContext(message, {
        currentHtml: getHtml(),
      });
      if (reply) {
        writeOutput(reply, false);
      }
      return;
    }
    writeOutput(t('Thinking...', 'Soch raha hoon...'), shouldSpeak);
    try {
      const response = await fetch('/html-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          html: getHtml(),
          language: lang(),
        }),
      });
      const data = await response.json();
      if (!data.success) throw new Error(data.error || 'Chat failed.');
      if (data.memory) state.memory = data.memory;
      const reply = data.reply || t('I do not have a reply yet.', 'Abhi mere paas jawab nahi hai.');
      writeOutput(reply, shouldSpeak);
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  function ensureAudio() {
    if (!state.audioCtx) state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (state.audioCtx.state === 'suspended') state.audioCtx.resume().catch(() => {});
    return state.audioCtx;
  }

  function playTone(freq, duration, offset = 0, type = 'sine', pan = 0) {
    const ctx = ensureAudio();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    const panner = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.value = 0.045;
    osc.connect(gain);
    if (panner) {
      panner.pan.value = Math.max(-1, Math.min(1, pan));
      gain.connect(panner);
      panner.connect(ctx.destination);
    } else {
      gain.connect(ctx.destination);
    }
    const start = ctx.currentTime + offset;
    osc.start(start);
    gain.gain.exponentialRampToValueAtTime(0.001, start + duration);
    osc.stop(start + duration);
  }

  let _sonifyTimer = null;

  function sonifyHtml() {
    cancelSpeech();
    if (_sonifyTimer) { clearTimeout(_sonifyTimer); _sonifyTimer = null; }
    const doc = previewDocument();
    const STRUCTURAL_TAGS = new Set(['header', 'nav', 'main', 'section', 'article', 'form', 'footer', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'button', 'a', 'img']);
    const FREQ_MAP = { header: 520, nav: 480, main: 400, section: 440, article: 440, form: 500, footer: 360, h1: 600, h2: 560, h3: 520, h4: 500, h5: 480, h6: 460, button: 700, a: 650, img: 820 };
    const WAVE_MAP = { button: 'square', a: 'triangle', img: 'sawtooth' };

    function collectStructural(node, depth) {
      const items = [];
      if (!node || !node.children) return items;
      for (const child of node.children) {
        const tag = child.tagName ? child.tagName.toLowerCase() : '';
        if (STRUCTURAL_TAGS.has(tag)) {
          items.push({ tag, depth: Math.min(depth, 5) });
          items.push(...collectStructural(child, depth + 1));
        } else {
          items.push(...collectStructural(child, depth));
        }
      }
      return items;
    }

    const items = collectStructural(doc.body, 0);
    if (!items.length) {
      speak(t('No HTML structure found to sonify.', 'Sonify karne ke liye HTML structure nahi mila.'));
      return;
    }
    const capped = items.slice(0, 20);
    const GAP = 0.10;
    const DURATION = 0.09;
    const totalTime = (capped.length * GAP + DURATION).toFixed(1);
    writeOutput(t(`Sonifying ${capped.length} structural elements (${totalTime}s).`, `${capped.length} structural elements sonify ho rahe hain (${totalTime}s).`));

    capped.forEach((item, index) => {
      const freq = (FREQ_MAP[item.tag] || 400) - item.depth * 40;
      const pan = Math.max(-1, Math.min(1, (item.depth - 2) / 3));
      const wave = WAVE_MAP[item.tag] || 'sine';
      playTone(Math.max(200, freq), DURATION, index * GAP, wave, pan);
    });

    _sonifyTimer = setTimeout(() => {
      _sonifyTimer = null;
      const summary = t(
        `Done. ${capped.length} elements: ${[...new Set(capped.map(i => i.tag))].join(', ')}.`,
        `Ho gaya. ${capped.length} elements: ${[...new Set(capped.map(i => i.tag))].join(', ')}.`
      );
      speak(summary);
    }, Math.ceil(capped.length * GAP * 1000) + 200);
  }
  const SNIPPET_STORAGE_KEY = 'codeup_snippets';
  const MAX_SNIPPETS = 30;

  function sanitizeSnippetName(name) {
    return (name || '').replace(/[^a-zA-Z0-9 _-]/g, '').trim().slice(0, 60).toLowerCase();
  }

  function loadSnippets() {
    try { return JSON.parse(localStorage.getItem(SNIPPET_STORAGE_KEY) || '{}'); } catch (e) { return {}; }
  }

  function persistSnippets(snippets) {
    try { localStorage.setItem(SNIPPET_STORAGE_KEY, JSON.stringify(snippets)); } catch (e) {}
  }

  function saveSnippet(name) {
    const safeName = sanitizeSnippetName(name);
    if (!safeName) { speak(t('Please provide a snippet name.', 'Snippet ka naam bataiye.')); return; }
    const html = getHtml();
    if (!html.trim()) { speak(t('Cannot save an empty page as a snippet.', 'Khaali page snippet mein save nahi hota.')); return; }
    const snippets = loadSnippets();
    const exists = safeName in snippets;
    if (exists) {
      snippets[safeName] = { html, saved: new Date().toISOString() };
      persistSnippets(snippets);
      speak(t(`Updated snippet: ${safeName}.`, `Snippet update ho gaya: ${safeName}.`));
    } else {
      if (Object.keys(snippets).length >= MAX_SNIPPETS) {
        speak(t(`You have ${MAX_SNIPPETS} snippets already. Delete one first.`, `Aapke paas ${MAX_SNIPPETS} snippets hain. Pehle ek delete karein.`));
        return;
      }
      snippets[safeName] = { html, saved: new Date().toISOString() };
      persistSnippets(snippets);
      speak(t(`Saved snippet: ${safeName}.`, `Snippet save ho gaya: ${safeName}.`));
    }
    writeOutput(t(`Snippet "${safeName}" saved.`, `Snippet "${safeName}" save ho gaya.`));
    refreshSnippetSelect();
  }

  function listSnippets() {
    const snippets = loadSnippets();
    const names = Object.keys(snippets);
    if (!names.length) {
      writeOutput(t('No saved snippets yet.', 'Abhi koi snippet save nahi hai.'), true);
      return;
    }
    const list = names.map(n => `- ${n}`).join('\n');
    writeOutput(t(`Your snippets:\n${list}`, `Aapke snippets:\n${list}`), true);
  }

  function loadSnippet(name) {
    const safeName = sanitizeSnippetName(name);
    if (!safeName) { speak(t('Please say the snippet name.', 'Snippet ka naam bataiye.')); return; }
    const snippets = loadSnippets();
    if (!(safeName in snippets)) {
      const available = Object.keys(snippets);
      const suggestion = available.length ? ` Available: ${available.join(', ')}.` : '';
      speak(t(`Snippet "${safeName}" not found.${suggestion}`, `Snippet "${safeName}" nahi mila.${suggestion}`));
      return;
    }
    const currentHtml = getHtml();
    if (currentHtml.trim() && currentHtml !== starterHtml) {
      snapshotVersion('Before loading snippet');
    }
    setHtml(snippets[safeName].html);
    snapshotVersion(`Loaded snippet: ${safeName}`);
    writeOutput(t(`Loaded snippet: ${safeName}.`, `Snippet load ho gaya: ${safeName}.`), true);
  }

  function deleteSnippet(name) {
    const safeName = sanitizeSnippetName(name);
    const snippets = loadSnippets();
    if (!safeName || !(safeName in snippets)) {
      writeOutput(t(`Snippet "${safeName}" not found.`, `Snippet "${safeName}" nahi mila.`), true);
      return;
    }
    delete snippets[safeName];
    persistSnippets(snippets);
    writeOutput(t(`Deleted snippet: ${safeName}.`, `Snippet delete ho gaya: ${safeName}.`), true);
    refreshSnippetSelect();
  }

  function insertAtCursor(text) {
    const editor = getEditor();
    if (!editor) return;
    if (editor.__codeupMonacoEditor) {
      const monacoEditor = editor.__codeupMonacoEditor;
      const selection = monacoEditor.getSelection();
      monacoEditor.executeEdits('codeup-voice', [{ range: selection, text, forceMoveMarkers: true }]);
      monacoEditor.focus();
      return;
    }
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const source = editorValue(editor);
    const before = source.slice(0, start);
    const after = source.slice(end);
    setEditorValue(editor, before + text + after);
    editor.selectionStart = editor.selectionEnd = start + text.length;
    editor.focus();
    noteEditorChanged(editor, 'codeup_html_draft');
  }

  function escapeHtmlText(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .trim();
  }

  function insertHtmlNearEnd(text) {
    const editor = getEditor();
    if (!editor) return;
    let html = normalizeHtmlDocument(getHtmlSource());
    if (/<\/main\s*>/i.test(html)) {
      html = html.replace(/<\/main\s*>/i, () => `${text}\n</main>`);
    } else if (/<\/body\s*>/i.test(html)) {
      html = html.replace(/<\/body\s*>/i, () => `${text}\n</body>`);
    } else {
      html += `\n${text}`;
    }
    setEditorValue(editor, ensureManagedRefs(html, !!getCss().trim(), !!getJs().trim()));
    persistDrafts();
    state.pages[state.currentPage] = getHtml();
    scheduleAutosave();
    editor.focus();
  }

  function addHtmlFromSpeech(command) {
    const lower = command.toLowerCase();
    const heading = command.match(/(?:add|insert|write|heading|title|sheershak|heading)\s+(?:heading\s+|title\s+)?(.+)/i);
    const paragraph = command.match(/(?:add paragraph|insert paragraph|write paragraph|paragraph|para|anuched)\s+(.+)/i);
    const button = command.match(/(?:add|insert)\s+(?:a\s+)?button(?:\s+(?:called|named|that says|labelled|labeled)?\s*(.+))?$/i)
      || command.match(/(?:button|button jodo)\s+(.+)/i);
    if (button) {
      const label = escapeHtmlText(button[1] || 'New button') || 'New button';
      snapshotVersion('Before adding button');
      beginReplay('Before adding button');
      insertHtmlNearEnd(`\n<button type="button">${label}</button>`);
      finishReplay('After adding button');
      writeOutput(t('Button added.', 'Button add ho gaya.'), true);
      return true;
    }
    if (paragraph) {
      snapshotVersion('Before adding paragraph');
      insertAtCursor(`\n<p>${paragraph[1].trim()}</p>\n`);
      writeOutput(t('Paragraph added.', 'Paragraph add ho gaya.'), true);
      return true;
    }
    if (heading && !lower.includes('website')) {
      snapshotVersion('Before adding heading');
      insertAtCursor(`\n<h2>${heading[1].trim()}</h2>\n`);
      writeOutput(t('Heading added.', 'Heading add ho gayi.'), true);
      return true;
    }
    return false;
  }

  function setPageTitle(title) {
    beginReplay('Before inserting page title');
    const clean = (title || 'My Website').trim();
    let html = getHtmlSource();
    if (/<title\b[^>]*>[\s\S]*?<\/title>/i.test(html)) {
      html = html.replace(/<title\b[^>]*>[\s\S]*?<\/title>/i, `<title>${clean}</title>`);
    } else if (/<head\b[^>]*>/i.test(html)) {
      html = html.replace(/<head\b[^>]*>/i, (match) => `${match}\n  <title>${clean}</title>`);
    } else {
      html = `<!doctype html>\n<html lang="en">\n<head><title>${clean}</title><link rel="stylesheet" href="style.css"></head>\n<body>\n${html}\n<script src="script.js" defer></script>\n</body>\n</html>`;
    }
    const editor = getEditor();
    if (editor) setEditorValue(editor, ensureManagedRefs(html, !!getCss().trim(), !!getJs().trim()));
    persistDrafts();
    state.pages[state.currentPage] = getHtml();
    scheduleAutosave();
    finishReplay('After inserting page title');
    writeOutput(`Inserted page title: ${clean}.`, true);
  }

  function addStructureBlocks() {
    const block = [
      '<header class="site-header">',
      '  <h1>My Website</h1>',
      '  <nav aria-label="Main navigation"><a href="#home">Home</a> <a href="#contact">Contact</a></nav>',
      '</header>',
      '<main id="home">',
      '  <section class="hero" aria-labelledby="hero-heading">',
      '    <h2 id="hero-heading">Welcome</h2>',
      '    <p>This section introduces the website.</p>',
      '  </section>',
      '</main>',
      '<footer>',
      '  <p>Contact us to learn more.</p>',
      '</footer>',
    ].join('\n');
    snapshotVersion('Before inserting page structure');
    beginReplay('Before inserting page structure');
    activateTab('html');
    insertAtCursor('\n' + block + '\n');
    finishReplay('After inserting page structure');
    writeOutput('Inserted header, navigation, main, section, and footer landmarks.', true);
  }

  function addCardStyles() {
    snapshotVersion('Before inserting card styles');
    beginReplay('Before inserting card styles');
    appendCssRules([
      'body { background: #f7fbff; color: #17202a; }',
      '.hero, .card, section { border: 1px solid #d9e2ec; border-radius: 10px; padding: 24px; background: #ffffff; }',
      'button, .button { border: 0; border-radius: 8px; padding: 12px 18px; background: #2563eb; color: #ffffff; font-weight: 700; }',
      'button:focus-visible, a:focus-visible { outline: 3px solid #f59e0b; outline-offset: 3px; }',
    ]);
    finishReplay('After inserting card styles');
    activateTab('css');
    writeOutput('Inserted CSS for background, cards, buttons, and focus states.', true);
  }

  function addButtonInteraction() {
    snapshotVersion('Before adding button interaction');
    beginReplay('Before adding button interaction');
    if (!/<button\b[^>]*id=["']demo-action["']/i.test(getHtmlSource())) {
      activateTab('html');
      insertAtCursor('\n<button id="demo-action" type="button">Try interaction</button>\n<p id="demo-result" aria-live="polite"></p>\n');
    }
    const jsEl = getJsEditor();
    if (jsEl && !/demo-action/.test(getJs())) {
      setEditorValue(jsEl, getJs().trim() + (getJs().trim() ? '\n\n' : '') +
        "var demoButton = document.getElementById('demo-action');\n" +
        "var demoResult = document.getElementById('demo-result');\n" +
        "if (demoButton && demoResult) {\n" +
        "  demoButton.addEventListener('click', function () {\n" +
        "    demoResult.textContent = 'The button interaction works.';\n" +
        "  });\n" +
        "}");
      persistDrafts();
      state.pages[state.currentPage] = getHtml();
      scheduleAutosave();
    }
    finishReplay('After adding button interaction');
    activateTab('js');
    writeOutput('Added a button interaction with a click listener in JavaScript.', true);
  }

  function handleWebInsertCommand(command, lower) {
    const title = command.match(/\b(?:insert|add)\s+(?:page\s+)?title\s+(.+)/i);
    if (title) { setPageTitle(title[1]); return true; }
    if (/\b(insert|add)\b.*\bheader\b.*\bnav\b.*\bmain\b.*\bsection\b.*\bfooter\b/i.test(command)) {
      addStructureBlocks();
      return true;
    }
    if (lower.includes('insert card styles') || lower.includes('add card styles') || lower.includes('style cards')) {
      addCardStyles();
      return true;
    }
    if (lower.includes('button interaction') || lower.includes('click interaction')) {
      addButtonInteraction();
      return true;
    }
    return false;
  }

  async function walkthroughPageMap() {
    const html = getHtml();
    writeOutput(t('Reading page structure...', 'Page structure padh raha hoon...'));
    const token = startHeartbeat('Preparing walkthrough');
    try {
      const data = await apiJson('/walkthrough/page-map', {
        method: 'POST',
        body: JSON.stringify({ html }),
      });
      if (!isAsyncFresh(token)) return;
      state.walkthrough.active = true;
      state.walkthrough.mode = 'page-map';
      stopHeartbeat(token);
      writeOutput(data.summary, true);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  function findWalkthroughWatchpoint(element) {
    const wt = state.walkthrough;
    if (!wt.watchpointMode || !element) return null;
    const embedded = element.watchpoint || null;
    const match = wt.watchpoints.find(function (issue) {
      if (embedded && issue.id === embedded.id && issue.selector === embedded.selector) return true;
      return issue.selector && element.selector && issue.selector === element.selector;
    });
    return match || embedded;
  }

  function writeWalkthroughPosition(message, element) {
    const wt = state.walkthrough;
    const wp = findWalkthroughWatchpoint(element);
    if (!wp) {
      writeOutput(message, true);
      return;
    }
    const watchpointIndex = wt.watchpoints.findIndex(function (issue) {
      return issue.id === wp.id && issue.selector === wp.selector;
    });
    wt.currentIssueIndex = watchpointIndex >= 0 ? watchpointIndex : 0;
    writeOutput(
      message + ' Accessibility watchpoint: ' + wp.description + ' Say "fix this issue" to apply a suggested repair.',
      true
    );
  }

  async function walkthroughKeyboardStart() {
    const html = getHtml();
    writeOutput(t('Starting keyboard journey...', 'Keyboard journey shuru ho rahi hai...'));
    const token = startHeartbeat('Preparing keyboard journey');
    try {
      const data = await apiJson('/walkthrough/keyboard-journey', {
        method: 'POST',
        body: JSON.stringify({ html }),
      });
      if (!isAsyncFresh(token)) return;
      state.walkthrough.active = true;
      state.walkthrough.mode = 'keyboard-journey';
      state.walkthrough.journeyElements = data.elements || [];
      state.walkthrough.journeyIndex = data.index;
      stopHeartbeat(token);
      writeWalkthroughPosition(data.message, state.walkthrough.journeyElements[data.index]);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  async function walkthroughKeyboardMove(direction) {
    const html = getHtml();
    const wt = state.walkthrough;
    if (!wt.journeyElements.length) {
      await walkthroughKeyboardStart();
      return;
    }
    try {
      const data = await apiJson('/walkthrough/keyboard-move', {
        method: 'POST',
        body: JSON.stringify({ html, index: wt.journeyIndex, direction }),
      });
      wt.journeyIndex = data.index;
      writeWalkthroughPosition(data.message, data.element);
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  async function walkthroughPauseOnIssues() {
    const html = getHtml();
    const token = startHeartbeat('Checking accessibility watchpoints');
    try {
      const data = await apiJson('/walkthrough/watchpoints', {
        method: 'POST',
        body: JSON.stringify({ html }),
      });
      if (!isAsyncFresh(token)) return;
      state.walkthrough.active = true;
      state.walkthrough.watchpointMode = true;
      state.walkthrough.watchpoints = data.watchpoints || [];
      state.walkthrough.watchpointIndex = 0;
      if (!data.watchpoints || !data.watchpoints.length) {
        stopHeartbeat(token);
        writeOutput(t('No accessibility watchpoints found. The page passes all current checks.', 'Koi accessibility issue nahi mila.'), true);
        return;
      }
      stopHeartbeat(token);
      writeOutput(t(
        'Watchpoint mode enabled. Navigating will pause on elements with accessibility issues. Say "start keyboard journey" or "next interactive element" to begin.',
        'Watchpoint mode on hai. Navigation accessibility issues par rukegi.'
      ), true);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  async function walkthroughListWatchpoints() {
    const html = getHtml();
    try {
      const data = await apiJson('/walkthrough/watchpoints', {
        method: 'POST',
        body: JSON.stringify({ html }),
      });
      state.walkthrough.watchpoints = data.watchpoints || [];
      writeOutput(data.message, true);
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  async function walkthroughExplainIssue() {
    const html = getHtml();
    const wt = state.walkthrough;
    try {
      const data = await apiJson('/walkthrough/explain', {
        method: 'POST',
        body: JSON.stringify({ html, issue_index: wt.currentIssueIndex }),
      });
      if (data.can_autofix) {
        writeOutput(data.message + ' Say "fix this issue" to apply a suggested repair.', true);
      } else {
        writeOutput(data.message, true);
      }
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  async function walkthroughFixIssue() {
    const html = getHtml();
    const wt = state.walkthrough;
    wt.htmlBeforeFix = html;
    beginReplay('Before walkthrough fix');
    const token = startHeartbeat('Fixing walkthrough issue');
    try {
      const data = await apiJson('/walkthrough/fix', {
        method: 'POST',
        body: JSON.stringify({ html, issue_index: wt.currentIssueIndex }),
      });
      if (!isAsyncFresh(token)) return;
      if (data.success && data.fixed_html) {
        snapshotVersion('Before walkthrough fix');
        setHtml(data.fixed_html);
        snapshotVersion('Applied walkthrough fix');
        finishReplay('After walkthrough fix');
        let msg = data.message;
        if (data.score_before !== undefined && data.score_after !== undefined) {
          msg += ` Accessibility score changed from ${data.score_before} to ${data.score_after}.`;
        }
        msg += ' Say "compare accessibility before and after" to hear the full comparison.';
        writeOutput(msg, true);
        try { await publish(data.fixed_html); } catch (e) {}
        stopHeartbeat(token);
        await checkWatchpoints('Walkthrough fix');
      } else {
        stopHeartbeat(token);
        writeOutput(data.message, true);
      }
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  async function walkthroughCompare() {
    const wt = state.walkthrough;
    const htmlAfter = getHtml();
    const htmlBefore = wt.htmlBeforeFix;
    if (!htmlBefore) {
      if (state.replay.before && state.replay.after) {
        await narrateReplay('compare accessibility before and after', 'Accessibility comparison');
        return;
      }
      writeOutput(t('No before version available. Fix an issue first, then compare.', 'Pehle koi issue fix karein, phir compare karein.'), true);
      return;
    }
    const token = startHeartbeat('Comparing accessibility');
    try {
      const data = await apiJson('/walkthrough/compare', {
        method: 'POST',
        body: JSON.stringify({ html_before: htmlBefore, html_after: htmlAfter }),
      });
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(data.message, true);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message, true);
    }
  }

  function walkthroughStop() {
    state.walkthrough.active = false;
    state.walkthrough.mode = null;
    state.walkthrough.watchpointMode = false;
    state.walkthrough.journeyElements = [];
    state.walkthrough.journeyIndex = -1;
    state.walkthrough.watchpoints = [];
    state.walkthrough.watchpointIndex = 0;
    state.walkthrough.currentIssueIndex = 0;
    writeOutput(t('Walkthrough stopped.', 'Walkthrough band ho gaya.'), true);
  }
  const tutorialOrder = ['html_basics', 'structure', 'css_basics', 'javascript_basics', 'accessibility_repair', 'export_share'];

  function updateTutorialPanel(message) {
    const panel = $('tutorialPanel');
    const status = $('tutorialStatus');
    if (panel) panel.dataset.active = state.tutorial.active ? 'true' : 'false';
    if (status) status.textContent = message || 'Type start tutorial for an audio-first website-building lesson.';
  }

  async function loadTutorialModules() {
    if (state.tutorial.modules.length) return state.tutorial.modules;
    try {
      const data = await apiJson('/tutorial/modules');
      state.tutorial.modules = data.modules || [];
    } catch (error) {
      state.tutorial.modules = [];
    }
    return state.tutorial.modules;
  }

  function currentTutorialModule() {
    return state.tutorial.modules[state.tutorial.index] || null;
  }

  async function startTutorial(topic) {
    const requested = (topic || '').toLowerCase();
    const trackMatch = requested.match(/start\s+(?:the\s+)?(html|css|javascript|js|accessibility|forms?|export)\s+tutorial/);
    if (trackMatch) { await startTrack(normalizeTrack(trackMatch[1])); return; }
    await loadTutorialModules();
    state.tutorial.active = true;
    if (requested.includes('css')) state.tutorial.index = tutorialOrder.indexOf('css_basics');
    else if (requested.includes('javascript') || requested.includes('js')) state.tutorial.index = tutorialOrder.indexOf('javascript_basics');
    else if (requested.includes('accessibility')) state.tutorial.index = tutorialOrder.indexOf('accessibility_repair');
    else if (requested.includes('html')) state.tutorial.index = tutorialOrder.indexOf('html_basics');
    if (state.tutorial.index < 0) state.tutorial.index = 0;
    state.tutorial.current = tutorialOrder[state.tutorial.index];
    const module = currentTutorialModule();
    const tour = 'Guided tutorial. We will build a website, ask for a code map, edit it, check accessibility, then export it. Say "next" to move on, "repeat" to hear the step again, or "exit tutorial" to stop.';
    const msg = `${tour}\n\nStep 1 â€” ${module.title}. ${module.explanation} Say or type exactly: ${module.command}. Then I will check your work.`;
    updateTutorialPanel(msg);
    writeOutput(msg, true);
  }

  async function validateTutorialProgress(command) {
    if (!state.tutorial.active || isTutorialControlCommand(command.toLowerCase())) return;
    const module = currentTutorialModule();
    if (!module) return;
    const token = nextAsyncToken();
    try {
      const data = await apiJson('/tutorial/validate', {
        method: 'POST',
        body: JSON.stringify({ module: module.id, html: getHtmlSource(), css: getCss(), js: getJs() }),
      });
      if (!isAsyncFresh(token)) return;
      state.tutorial.lastValidation = data;
      const visibleMessage = data.valid ? (data.message || '').replace(module.title, 'this lesson') : data.message;
      updateTutorialPanel(visibleMessage);
      if (data.valid) {
        const completed = loadJsonStore('codeup_tutorial_completed', {});
        completed[module.id] = new Date().toISOString();
        saveJsonStore('codeup_tutorial_completed', completed);
        writeOutput(`${data.message} Say continue for the next module, practise again, recap, hint, or exit tutorial.`, true);
      } else {
        writeOutput(`${data.message} Say hint, repeat, try again, or exit tutorial.`, true);
      }
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      writeOutput(error.message, true);
    }
  }

  async function continueTutorial() {
    await loadTutorialModules();
    state.tutorial.active = true;
    state.tutorial.index = Math.min(state.tutorial.modules.length - 1, state.tutorial.index + 1);
    state.tutorial.current = tutorialOrder[state.tutorial.index] || (currentTutorialModule() || {}).id || '';
    const module = currentTutorialModule();
    const msg = module ? `${module.title}. ${module.explanation} Say or type exactly: ${module.command}.` : 'Tutorial complete. Start coding whenever you are ready.';
    updateTutorialPanel(msg);
    writeOutput(msg, true);
  }

  function tutorialHint() {
    const module = currentTutorialModule();
    const msg = module ? `Hint: ${module.hint}` : 'Start tutorial to get a hint.';
    updateTutorialPanel(msg);
    writeOutput(msg, true);
  }

  function tutorialRecap() {
    const completed = loadJsonStore('codeup_tutorial_completed', {});
    const done = Object.keys(completed);
    const msg = done.length
      ? `Tutorial recap. Completed modules: ${done.join(', ')}. Current module: ${(currentTutorialModule() || {}).title || 'none'}.`
      : `Tutorial recap. No modules completed yet. Current module: ${(currentTutorialModule() || {}).title || 'none'}.`;
    updateTutorialPanel(msg);
    writeOutput(msg, true);
  }

  function exitTutorial() {
    state.tutorial.active = false;
    updateTutorialPanel('Tutorial paused. Type start tutorial to resume.');
    writeOutput('Tutorial paused. You are back in normal coding mode.', true);
  }

  function isTutorialControlCommand(lower) {
    return /^(continue|next|next step|try again|practise again|practice again|recap|hint|repeat|give me an example|read my code|exit tutorial|start coding)$/.test(lower)
      || lower === 'tutorial' || lower === 'start tutorial' || /^practi[cs]e\s+(html|css|javascript|accessibility)$/.test(lower);
  }

  function isLocalMetaCommand(lower) {
    return /^(remember this as|save this command as|use macro|run macro|list macros|delete macro|bookmark this|read from bookmark|list bookmarks|delete bookmark|where am i|read breadcrumb|what am i editing|restore my last work|what did i last work on|compare before and after|read before and after|replay my mistake|what changed|explain this change|is this risky|show changed lines|read only what changed|compare preview changes|compare code changes|give me a code map|map this website|website map|project map|list all buttons|list all forms|read the html|read the css|read the javascript|explain simply|explain this error|why is this broken|step narration|learning notes|accessibility map|review project|describe preview|say more)/.test(lower);
  }

  function isCodeMapQuestion(lower) {
    return lower.includes('map this website')
      || lower.includes('website map')
      || lower.includes('project map')
      || lower.includes('explain the structure')
      || lower.includes('summarize structure')
      || lower.includes('summarise structure')
      || lower.includes('what files are here')
      || lower.includes('what sections')
      || lower.includes('what is inside')
      || lower.includes('what comes after')
      || lower.includes('list all buttons')
      || lower.includes('list all forms')
      || lower.includes('what css styles')
      || lower.includes('what javascript controls')
      || lower.includes('how deeply nested')
      || lower.includes('read the page structure');
  }

  function isMacroWorthyCommand(command) {
    const lower = command.toLowerCase();
    if (isLocalMetaCommand(lower) || isCodeMapQuestion(lower)) return false;
    return isBuildIntent(command)
      || /^(insert|add)\b/.test(lower)
      || lower.includes('futuristic')
      || lower.includes('dark mode')
      || lower.includes('more beautiful')
      || lower.includes('more colorful')
      || lower.includes('more colourful')
      || lower.includes('improve the design')
      || lower.includes('add animation')
      || lower.includes('add javascript')
      || lower.includes('add interactivity');
  }

  function shouldValidateTutorialCommand(lower) {
    if (!state.tutorial.active || isLocalMetaCommand(lower)) return false;
    return /^(insert|add|style|fix accessibility|fix the accessibility|run preview|export|generate|make|create|build)\b/.test(lower);
  }

  async function handleTutorialCommand(command) {
    const lower = command.toLowerCase();
    if (/\bstart\s+web\s+tutorial\b/.test(lower) || /\bbuild\s+my\s+first\s+website\b/.test(lower) || /\bbuild\s+(?:a\s+)?website\s+by\s+ear\b/.test(lower)) {
      await startGuidedBuild();
      return true;
    }
    if (/^start\s+(?:the\s+)?(html|css|javascript|accessibility|forms?|export)\s+tutorial$/.test(lower)) {
      await startTutorial(lower);
      return true;
    }
    if (state.track && state.track.active) {
      if (lower === 'next' || lower === 'next step' || lower === 'continue') return trackNext();
      if (lower === 'hint') return trackHint();
      if (lower === 'recap') return trackRecap();
      if (lower === 'repeat' || lower === 'try again') return trackRepeat();
      if (lower === 'exit tutorial' || lower === 'start coding') return trackExit();
    }
    if (lower === 'start tutorial' || lower === 'tutorial' || /^practi[cs]e\s+/.test(lower)) { await startTutorial(lower); return true; }
    if (!state.tutorial.active && !isTutorialControlCommand(lower)) return false;
    if (lower === 'continue' || lower === 'next' || lower === 'next step') { await continueTutorial(); return true; }
    if (lower === 'try again' || lower === 'practise again' || lower === 'practice again' || lower === 'repeat' || lower === 'give me an example') {
      const module = currentTutorialModule();
      const msg = module ? `Try this exact command: ${module.command}.` : 'Start tutorial first.';
      writeOutput(msg, true);
      updateTutorialPanel(msg);
      return true;
    }
    if (lower === 'hint') { tutorialHint(); return true; }
    if (lower === 'recap') { tutorialRecap(); return true; }
    if (lower === 'read my code') { readCode('all'); return true; }
    if (lower === 'exit tutorial' || lower === 'start coding') { exitTutorial(); return true; }
    return false;
  }
  function macroName(command) {
    const match = command.match(/\b(?:as|macro)\s+(.+)$/i);
    return (match ? match[1] : '').trim();
  }

  async function saveMacro(command) {
    const name = macroName(command);
    if (!name || !state.lastCommand) {
      writeOutput('No recent website command to remember yet.', true);
      return true;
    }
    const macros = loadJsonStore('codeup_voice_macros', {});
    macros[name] = { command: state.lastCommand, savedAt: new Date().toISOString() };
    saveJsonStore('codeup_voice_macros', macros);
    writeOutput(`Saved macro "${name}" as: ${state.lastCommand}`, true);
    return true;
  }

  async function runMacro(command) {
    const name = macroName(command);
    const macros = loadJsonStore('codeup_voice_macros', {});
    if (!name || !macros[name]) {
      writeOutput(`Macro "${name}" not found.`, true);
      return true;
    }
    writeOutput(`Running macro "${name}": ${macros[name].command}`, true);
    await handleStudentText(macros[name].command);
    return true;
  }

  function listMacros() {
    const macros = loadJsonStore('codeup_voice_macros', {});
    const names = Object.keys(macros);
    writeOutput(names.length ? `Macros:\n${names.map(name => `- ${name}: ${macros[name].command}`).join('\n')}` : 'No macros saved yet.', true);
    return true;
  }

  function deleteMacro(command) {
    const name = macroName(command);
    const macros = loadJsonStore('codeup_voice_macros', {});
    if (name && macros[name]) {
      delete macros[name];
      saveJsonStore('codeup_voice_macros', macros);
      writeOutput(`Deleted macro "${name}".`, true);
    } else {
      writeOutput(`Macro "${name}" not found.`, true);
    }
    return true;
  }

  function bookmarkName(command) {
    const match = command.match(/\bas\s+(.+)$/i)
      || command.match(/\bbookmark\s+(.+)$/i);
    return (match ? match[1] : 'bookmark').trim() || 'bookmark';
  }

  function saveBookmark(command) {
    const name = bookmarkName(command);
    const sectionMatch = command.match(/\bbookmark\s+(?:this|the|current|that)?\s*(.+?)\s+as\s+/i);
    const section = (sectionMatch ? sectionMatch[1] : '').trim();
    const bookmarks = loadJsonStore('codeup_bookmarks', {});
    bookmarks[name] = {
      section,
      output: state.lastOutput,
      codeMap: state.lastCodeMap,
      issue: state.lastPauseReason || (((state.lastAudit || {}).issues || [])[0] || {}).description || '',
      editor: state.activeTab || 'html',
      line: currentEditorLine(),
      savedAt: new Date().toISOString(),
    };
    saveJsonStore('codeup_bookmarks', bookmarks);
    writeOutput(`Bookmarked "${name}".`, true);
    return true;
  }

  function readBookmark(command) {
    const name = bookmarkName(command);
    const bookmarks = loadJsonStore('codeup_bookmarks', {});
    const item = bookmarks[name];
    if (!item) {
      writeOutput(`Bookmark "${name}" not found.`, true);
      return true;
    }
    const msg = `Bookmark ${name}. Editor ${item.editor}, line ${item.line}. ${item.issue || item.output || item.codeMap || 'No saved details.'}`;
    writeOutput(msg, true);
    return true;
  }

  function listBookmarks() {
    const bookmarks = loadJsonStore('codeup_bookmarks', {});
    const names = Object.keys(bookmarks);
    writeOutput(names.length ? `Bookmarks:\n${names.map(name => `- ${name}`).join('\n')}` : 'No bookmarks saved yet.', true);
    return true;
  }

  function deleteBookmark(command) {
    const name = bookmarkName(command);
    const bookmarks = loadJsonStore('codeup_bookmarks', {});
    if (name && bookmarks[name]) {
      delete bookmarks[name];
      saveJsonStore('codeup_bookmarks', bookmarks);
      writeOutput(`Deleted bookmark "${name}".`, true);
    } else {
      writeOutput(`Bookmark "${name}" not found.`, true);
    }
    return true;
  }

  function currentEditorLine() {
    const which = state.activeTab || 'html';
    const editor = which === 'css' ? getCssEditor() : which === 'js' ? getJsEditor() : getEditor();
    if (!editor) return 1;
    return editor.value.slice(0, editor.selectionStart || 0).split('\n').length;
  }

  function breadcrumb() {
    const which = state.activeTab || 'html';
    const editor = which === 'css' ? getCssEditor() : which === 'js' ? getJsEditor() : getEditor();
    const line = currentEditorLine();
    const lines = ((editor || {}).value || '').split('\n');
    const current = lines[line - 1] || '';
    let msg = '';
    if (which === 'html') {
      const before = lines.slice(0, line).join('\n');
      const tags = [...before.matchAll(/<\/?([a-zA-Z][\w-]*)\b[^>]*>/g)]
        .map(m => ({ tag: m[1].toLowerCase(), close: m[0].startsWith('</') }))
        .reduce((stack, item) => {
          if (item.close) {
            const idx = stack.lastIndexOf(item.tag);
            if (idx !== -1) stack.splice(idx);
          } else if (!['meta', 'link', 'img', 'input', 'br', 'hr'].includes(item.tag)) stack.push(item.tag);
          return stack;
        }, []);
      msg = `HTML, ${tags.join(' landmark, ') || 'document'}, line ${line}. Current text: ${current.trim() || 'blank line'}.`;
    } else if (which === 'css') {
      const selectorLine = [...lines.slice(0, line).reverse()].find(text => text.includes('{')) || '';
      const selector = selectorLine.split('{')[0].trim() || 'current selector';
      const prop = (current.match(/([\w-]+)\s*:/) || [])[1] || 'property';
      msg = `CSS, selector ${selector}, property ${prop}, line ${line}.`;
    } else {
      const fnLine = [...lines.slice(0, line).reverse()].find(text => /function\s+|addEventListener|=>/.test(text)) || '';
      const fn = (fnLine.match(/function\s+([A-Za-z0-9_]+)/) || fnLine.match(/([A-Za-z0-9_]+)\.addEventListener/) || [])[1] || 'top level script';
      msg = `JavaScript, ${fn}, line ${line}.`;
    }
    writeOutput(msg, true);
    return true;
  }

  async function explainErrors(fixFirst = false) {
    if (fixFirst) beginReplay('Before fix and explain');
    if (fixFirst) await applyAuditFix('', false);
    const token = nextAsyncToken();
    try {
      const data = await apiJson('/explain-errors', {
        method: 'POST',
        body: JSON.stringify({ html: getHtmlSource(), css: getCss(), js: getJs() }),
      });
      if (!isAsyncFresh(token)) return true;
      if (fixFirst) finishReplay('After fix and explain');
      writeOutput(data.message, true);
    } catch (error) {
      if (!isAsyncFresh(token)) return true;
      writeOutput(error.message, true);
    }
    return true;
  }

  async function checkWatchpoints(context) {
    if (!state.watchpointRules.length) return;
    try {
      const data = await apiJson('/watchpoints/check', {
        method: 'POST',
        body: JSON.stringify({ html: getHtml(), enabled: state.watchpointRules }),
      });
      if (data.paused) {
        state.lastPauseReason = `${context || 'Check'}: ${data.reason}`;
        const output = $('output');
        if (output && output.textContent.trim()) {
          output.textContent += `\n\n${state.lastPauseReason}`;
          state.lastOutput = output.textContent;
          speak(state.lastPauseReason);
        } else {
          writeOutput(state.lastPauseReason, true);
        }
      }
    } catch (error) {}
  }

  async function enableWatchpoint(command, slots = {}) {
    const type = slots.watchpoint || (/heading/i.test(command) ? 'heading_order'
      : /alt|image/i.test(command) ? 'image_alt'
      : /button/i.test(command) ? 'button_label'
      : /form|input|label/i.test(command) ? 'form_label'
      : /contrast/i.test(command) ? 'contrast'
      : 'accessibility');
    if (!state.watchpointRules.includes(type)) state.watchpointRules.push(type);
    saveJsonStore('codeup_watchpoints', state.watchpointRules);
    await walkthroughPauseOnIssues();
    await checkWatchpoints('Watchpoint armed');
    return true;
  }

  function restoreLastWork(describeOnly = false) {
    const saved = loadJsonStore('codeup_last_work', null);
    if (!saved) {
      writeOutput('No saved local work found yet.', true);
      return true;
    }
    if (!describeOnly) {
      loadGeneratedFiles({ html: saved.html || starterBodyHtml, css: saved.css || '', js: saved.js || '' });
      const pythonEl = getPythonEditor();
      if (pythonEl && saved.python) setEditorValue(pythonEl, saved.python);
      state.projectId = saved.projectId || state.projectId;
      state.projectName = saved.projectName || state.projectName;
      state.currentPage = saved.currentPage || state.currentPage;
      state.lastUrl = saved.previewUrl || state.lastUrl;
    }
    writeOutput(`Last work: ${saved.projectName || 'Untitled Project'}, saved ${saved.savedAt || 'recently'}. HTML ${String(saved.html || '').split('\n').length} lines, CSS ${String(saved.css || '').split('\n').length} lines, JavaScript ${String(saved.js || '').split('\n').length} lines.`, true);
    return true;
  }

  function restoreLocalFeatureState() {
    const watchpoints = loadJsonStore('codeup_watchpoints', []);
    state.watchpointRules = Array.isArray(watchpoints) ? watchpoints : [];
    const savedTrack = loadJsonStore('codeup_track_state', null);
    if (savedTrack && savedTrack.active && Array.isArray(savedTrack.steps) && savedTrack.steps.length) {
      state.track = {
        active: true,
        guided: !!savedTrack.guided,
        id: savedTrack.id || '',
        index: Math.min(Number(savedTrack.index) || 0, savedTrack.steps.length),
        steps: savedTrack.steps,
        title: savedTrack.title || 'Tutorial',
      };
      updateTutorialPanel(trackStepMessage());
    }    const saved = loadJsonStore('codeup_last_work', null);
    if (saved && saved.previewUrl && /^\/student-site\//.test(saved.previewUrl)) {
      state.lastUrl = saved.previewUrl;
      const frame = ensurePreviewFrame();
      if (frame && !frame.getAttribute('src')) frame.src = saved.previewUrl;
      markPreviewReady();
      const openBtn = $('sitePreviewOpenBtn');
      if (openBtn) {
        openBtn.disabled = false;
        openBtn.dataset.url = saved.previewUrl;
      }
    }
  }
  const TAB_IDS = { html: 'tabHtml', css: 'tabCss', js: 'tabJs', python: 'tabPython' };
  const PANEL_IDS = { html: 'panelHtml', css: 'panelCss', js: 'panelJs', python: 'panelPython' };

  function activateTab(name) {
    const target = TAB_IDS[name] ? name : 'html';
    state.activeTab = target;
    Object.keys(TAB_IDS).forEach((key) => {
      const tab = $(TAB_IDS[key]);
      const panel = $(PANEL_IDS[key]);
      const selected = key === target;
      if (tab) {
        tab.setAttribute('aria-selected', selected ? 'true' : 'false');
        tab.tabIndex = selected ? 0 : -1;
      }
      if (panel) {
        if (selected) panel.removeAttribute('hidden');
        else panel.setAttribute('hidden', '');
      }
    });
    const focusMap = { html: 'htmlEditor', css: 'cssEditor', js: 'jsEditor', python: 'pythonEditor' };
    const editor = $(focusMap[target]);
    if (editor && document.activeElement && /tab/i.test(document.activeElement.id || '')) editor.focus();
  }

  function setupTabs() {
    const order = ['html', 'css', 'js', 'python'];
    order.forEach((name) => {
      const tab = $(TAB_IDS[name]);
      if (!tab) return;
      tab.addEventListener('click', () => activateTab(name));
      tab.addEventListener('keydown', (event) => {
        const idx = order.indexOf(name);
        let nextName = null;
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') nextName = order[(idx + 1) % order.length];
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') nextName = order[(idx - 1 + order.length) % order.length];
        else if (event.key === 'Home') nextName = order[0];
        else if (event.key === 'End') nextName = order[order.length - 1];
        if (nextName) {
          event.preventDefault();
          activateTab(nextName);
          const nextTab = $(TAB_IDS[nextName]);
          if (nextTab) nextTab.focus();
        }
      });
    });
    activateTab('html');
  }

  function generateFromCommand() {
    const field = $('commandInput');
    const value = field ? field.value.trim() : '';
    if (!value) {
      writeOutput(t('Type what to build in the command box, then press Generate.', 'Command box mein likhiye kya banana hai, phir Generate dabaiye.'), true);
      if (field) field.focus();
      return;
    }
    buildWebsite(value, true);
  }
  function describeForSpeech(label, code) {
    const trimmed = (code || '').trim();
    if (!trimmed) return t(`The ${label} is empty.`, `${label} khaali hai.`);
    const lines = trimmed.split('\n').length;
    return t(
      `${label}, ${lines} line${lines === 1 ? '' : 's'}. ${trimmed}`,
      `${label}, ${lines} line. ${trimmed}`
    );
  }

  function readCode(target) {
    let which = target || state.activeTab || 'html';
    if (which === 'all') {
      const msg = [
        describeForSpeech('HTML', getHtmlSource()),
        describeForSpeech('CSS', getCss()),
        describeForSpeech('JavaScript', getJs()),
        describeForSpeech('Python', getPython()),
      ].join('\n\n');
      writeOutput(msg, true);
      return;
    }
    const map = {
      html: ['HTML', getHtmlSource()],
      css: ['CSS', getCss()],
      js: ['JavaScript', getJs()],
      python: ['Python', getPython()],
    };
    const entry = map[which] || map.html;
    activateTab(which);
    writeOutput(describeForSpeech(entry[0], entry[1]), true);
  }
  function buildCodeMap() {
    const doc = previewDocument();
    const sections = [];
    const landmarks = doc.body ? doc.body.querySelectorAll('header,nav,main,section,article,aside,footer,form') : [];
    landmarks.forEach((node) => {
      const tag = node.tagName.toLowerCase();
      const heading = node.querySelector('h1,h2,h3');
      const label = node.getAttribute('aria-label') || (heading ? heading.textContent.trim() : '') || '';
      sections.push(`${tag}${label ? ': ' + label : ''}`);
    });
    const headings = [...doc.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(
      (h) => `${h.tagName.toUpperCase()} ${h.textContent.replace(/\s+/g, ' ').trim()}`
    );

    const css = getCss() || (getHtmlSource().match(/<style\b[^>]*>([\s\S]*?)<\/style>/i) || [])[1] || '';
    const selectors = [...new Set((css.match(/[^{}]+(?=\s*\{)/g) || [])
      .map((s) => s.replace(/\s+/g, ' ').trim())
      .filter((s) => s && !s.startsWith('@') && !s.startsWith('/*')))].slice(0, 14);

    const js = getJs() || (getHtmlSource().match(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/i) || [])[1] || '';
    const fns = [...new Set([
      ...(js.match(/function\s+([A-Za-z0-9_]+)/g) || []).map((m) => m.replace(/function\s+/, '') + '()'),
      ...(js.match(/(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(/g) || [])
        .map((m) => m.replace(/(?:const|let|var)\s+/, '').replace(/\s*=.*/, '') + '()'),
    ])].slice(0, 14);
    const events = [...new Set((js.match(/addEventListener\(\s*['"]([a-z]+)['"]/g) || [])
      .map((m) => m.replace(/addEventListener\(\s*['"]/, '').replace(/['"]/, '')))].slice(0, 10);

    return { sections, headings, selectors, fns, events };
  }

  async function codeMap(query = '') {
    const token = nextAsyncToken();
    try {
      const data = await apiJson('/code-map', {
        method: 'POST',
        body: JSON.stringify({ html: getHtmlSource(), css: getCss(), js: getJs(), query }),
      });
      if (!isAsyncFresh(token)) return;
      state.lastCodeMap = data.summary || '';
      writeOutput(state.lastCodeMap, false);
      const spoken = data.answer || `Code map. ${data.landmarks.length} landmarks, ${data.headings.length} headings, ${data.buttons.length} buttons, ${data.forms.length} forms, ${data.css.length} CSS rules, and ${data.javascript.functions.length} JavaScript functions. Full map is on screen.`;
      speak(spoken);
      return;
    } catch (error) {}

    if (!isAsyncFresh(token)) return;
    const map = buildCodeMap();
    const detail = [
      t('CODE MAP', 'CODE MAP'),
      '',
      t('HTML sections:', 'HTML sections:'),
      ...(map.sections.length ? map.sections.map((s) => '  - ' + s) : ['  (none found)']),
      '',
      t('Headings:', 'Headings:'),
      ...(map.headings.length ? map.headings.map((h) => '  - ' + h) : ['  (none found)']),
      '',
      t('CSS selectors:', 'CSS selectors:'),
      ...(map.selectors.length ? map.selectors.map((s) => '  - ' + s) : ['  (none found)']),
      '',
      t('JavaScript functions:', 'JavaScript functions:'),
      ...(map.fns.length ? map.fns.map((f) => '  - ' + f) : ['  (none found)']),
      '',
      t('JavaScript events:', 'JavaScript events:'),
      ...(map.events.length ? map.events.map((e) => '  - ' + e) : ['  (none found)']),
    ].join('\n');
    state.lastCodeMap = detail;
    writeOutput(detail, false);
    const spoken = t(
      `Code map. ${map.sections.length} HTML sections, ${map.headings.length} headings, ${map.selectors.length} CSS rules, and ${map.fns.length} JavaScript functions handling ${map.events.length} events. Full map is on screen.`,
      `Code map. ${map.sections.length} HTML sections, ${map.headings.length} headings, ${map.selectors.length} CSS rules, aur ${map.fns.length} JavaScript functions. Poora map screen par hai.`
    );
    speak(spoken);
  }

  async function projectText(endpoint, stateKey, label, extra = {}) {
    const token = nextAsyncToken();
    writeOutput(`${label}...`);
    try {
      const data = await apiJson(endpoint, {
        method: 'POST',
        body: JSON.stringify(projectPayload(extra)),
      });
      if (!isAsyncFresh(token)) return '';
      const text = data.text || data.summary || data.explanation || data.review || data.description || '';
      if (!text) throw new Error(`${label} returned no text.`);
      state[stateKey] = text;
      writeOutput(text, false);
      speakChunked(data.speech || text);
      return text;
    } catch (error) {
      if (!isAsyncFresh(token)) return '';
      writeOutput(error.message || `${label} failed.`, true);
      return '';
    }
  }

  function getPythonInputs() {
    return (state.pythonInputs || []).map((value) => String(value));
  }

  function savePythonInputs() {
    state.pythonInputs = getPythonInputs();
    saveJsonStore('codeup_python_inputs', state.pythonInputs);
  }

  function renderPythonInputs() {
    const list = $('pythonInputList');
    const count = $('pythonInputCount');
    const values = getPythonInputs();
    if (count) count.textContent = values.length ? `${values.length} queued input${values.length === 1 ? '' : 's'}.` : 'No queued inputs.';
    if (!list) return;
    list.textContent = '';
    values.forEach((value, index) => {
      const item = document.createElement('li');
      item.textContent = `Input ${index + 1}: ${value}`;
      list.appendChild(item);
    });
    if (!values.length) {
      const item = document.createElement('li');
      item.textContent = 'No input values added yet.';
      list.appendChild(item);
    }
  }

  function addPythonInputValue(value, shouldSpeak = true) {
    const clean = String(value || '').replace(/[\r\n]+/g, ' ').trim();
    if (!clean) {
      writeOutput('Type an input value first.', true);
      return false;
    }
    state.pythonInputs = getPythonInputs();
    if (state.pythonInputs.length >= PYTHON_INPUT_LIMIT) {
      writeOutput(`CodeUp can queue up to ${PYTHON_INPUT_LIMIT} Python inputs for one run. Clear old inputs before adding more.`, true);
      return false;
    }
    if (clean.length > PYTHON_INPUT_CHAR_LIMIT) {
      writeOutput(`That Python input is too long. Keep each input to ${PYTHON_INPUT_CHAR_LIMIT} characters or fewer.`, true);
      return false;
    }
    state.pythonInputs.push(clean);
    savePythonInputs();
    renderPythonInputs();
    if (shouldSpeak) writeOutput(`Added Python input ${state.pythonInputs.length}: ${clean}.`, true);
    return true;
  }

  function addPythonInputFromUi() {
    const field = $('pythonInputValue');
    if (!field) return false;
    const ok = addPythonInputValue(field.value, true);
    if (ok) {
      field.value = '';
      field.focus();
    }
    return ok;
  }

  function clearPythonInputs(shouldSpeak = true) {
    state.pythonInputs = [];
    savePythonInputs();
    renderPythonInputs();
    if (shouldSpeak) writeOutput('Cleared queued Python inputs.', true);
    return true;
  }

  function isStarterOrExamplePython(code) {
    const current = String(code || '').trim();
    if (!current || current === starterPython.trim()) return true;
    return Object.keys(PYTHON_EXAMPLES).some((name) => current === PYTHON_EXAMPLES[name].code.trim());
  }

  function loadPythonExample(name, force = false) {
    const example = PYTHON_EXAMPLES[name];
    const editor = getPythonEditor();
    if (!example || !editor) return false;
    const current = getPython();
    if (!force && !isStarterOrExamplePython(current)) {
      writeOutput(`The Python editor already has your code. Clear it first, or say replace with the ${example.label} example.`, true);
      return false;
    }
    activateTab('python');
    setEditorValue(editor, example.code);
    try { sessionStorage.setItem('codeup_python_draft', editorValue(editor)); } catch (error) {}
    state.lastPythonRun = null;
    state.lastPythonError = '';
    state.lastPythonStepCursor = 0;
    state.lastPythonStateWatch = null;
    state.lastPythonStateKey = '';
    editor.focus();
    writeOutput(`Loaded Python ${example.label} example.`, true);
    return true;
  }

  function recordPythonHistory(kind, title, text) {
    const clean = String(text || '').trim();
    if (!clean) return;
    const item = {
      kind,
      title: title || kind,
      text: clean.slice(0, 1200),
      time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    state.pythonHistory = [item].concat(Array.isArray(state.pythonHistory) ? state.pythonHistory : []).slice(0, 12);
    saveJsonStore('codeup_python_history', state.pythonHistory);
    renderPythonHistory();
  }

  function renderPythonHistory() {
    const list = $('pythonHistoryList');
    if (!list) return;
    list.textContent = '';
    const items = Array.isArray(state.pythonHistory) ? state.pythonHistory : [];
    if (!items.length) {
      const item = document.createElement('li');
      item.textContent = 'No Python history yet. Run or analyze code to add entries.';
      list.appendChild(item);
      return;
    }
    items.forEach((entry) => {
      const item = document.createElement('li');
      const title = document.createElement('strong');
      title.textContent = `${entry.time || ''} ${entry.title || entry.kind || 'Python entry'}`.trim();
      const body = document.createElement('p');
      body.textContent = entry.text || '';
      item.appendChild(title);
      item.appendChild(body);
      list.appendChild(item);
    });
  }

  function clearPythonHistory() {
    state.pythonHistory = [];
    saveJsonStore('codeup_python_history', state.pythonHistory);
    renderPythonHistory();
    writeOutput('Cleared Python learning history.', true);
    return true;
  }

  function showPythonHistory() {
    renderPythonHistory();
    const items = Array.isArray(state.pythonHistory) ? state.pythonHistory : [];
    const text = items.length
      ? items.map((entry, index) => `${index + 1}. ${entry.title}: ${entry.text}`).join('\n\n')
      : 'No Python history yet. Run or analyze code to add entries.';
    writeOutput(text, true);
    return true;
  }

  function pythonPayload(extra = {}) {
    return Object.assign({ code: getPython(), language: lang(), inputs: getPythonInputs() }, extra);
  }

  function requirePythonCode() {
    if (getPython().trim()) return true;
    activateTab('python');
    writeOutput('The Python editor is empty. Type or dictate Python code first.', true);
    return false;
  }

  async function runPythonCode() {
    activateTab('python');
    if (!requirePythonCode()) return;
    const token = startHeartbeat('Running Python');
    writeOutput('Running Python...');
    try {
      const data = await apiJsonLoose('/python/run', {
        method: 'POST',
        body: JSON.stringify(pythonPayload()),
      });
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      state.lastPythonRun = data;
      if (data.success) {
        state.lastPythonError = '';
        const output = (data.output || '').trim();
        const inputBlock = data.input_summary ? `\n\nINPUTS\n${data.input_summary}` : '';
        const breakpointBlock = data.breakpoint && data.breakpoint.triggered
          ? `\n\nCONDITIONAL AUDIO BREAKPOINT\n${data.breakpoint.explanation || data.breakpoint.speech || ''}`
          : '';
        const visible = (output ? `PYTHON OUTPUT\n${output}` : 'PYTHON OUTPUT\nProgram finished with no output.') + inputBlock + breakpointBlock;
        writeOutput(visible, false);
        recordPythonHistory('run', data.breakpoint && data.breakpoint.triggered ? 'Run with breakpoint' : 'Run output', visible);
        speak(data.speech || (output ? `Program output: ${output}` : 'Program finished with no output.'));
      } else {
        state.lastPythonError = data.error || '';
        const inputBlock = data.input_summary ? `INPUTS\n${data.input_summary}` : '';
        const visible = ['PYTHON ERROR', data.error || 'The program stopped with an error.', data.explanation || '', inputBlock]
          .filter(Boolean)
          .join('\n');
        writeOutput(visible, false);
        recordPythonHistory('error', 'Python error', visible);
        speak(data.speech || data.explanation || data.error || 'The program stopped with an error.');
      }
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message || 'Python run failed.', true);
    }
  }

  async function runPythonWithInputs() {
    activateTab('python');
    const count = getPythonInputs().length;
    if (!count) {
      writeOutput('No inputs are queued yet. Add input values first, or run normally for code without input().', true);
      return;
    }
    await runPythonCode();
  }

  async function analyzePythonCode(mode = 'analyze') {
    activateTab('python');
    if (!requirePythonCode()) return;
    const token = startHeartbeat(mode === 'teach' ? 'Teaching Python code' : 'Analyzing Python code');
    try {
      const data = await apiJsonLoose('/python/analyze', {
        method: 'POST',
        body: JSON.stringify(pythonPayload({ mode, error: state.lastPythonError })),
      });
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      const text = data.analysis || data.speech || 'No Python analysis returned.';
      writeOutput(text, false);
      recordPythonHistory(mode === 'teach' ? 'teach' : 'analyze', mode === 'teach' ? 'Teaching explanation' : 'Code analysis', text);
      speakChunked(data.speech || text);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message || 'Python analysis failed.', true);
    }
  }

  async function pythonAudioCodeMap(query = '') {
    activateTab('python');
    if (!requirePythonCode()) return;
    const token = startHeartbeat('Mapping Python code');
    try {
      const data = await apiJsonLoose('/python/audio-code-map', {
        method: 'POST',
        body: JSON.stringify(pythonPayload({ query })),
      });
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      const text = data.reply || data.speech || 'No Python code map returned.';
      state.lastCodeMap = text;
      writeOutput(text, false);
      recordPythonHistory('code-map', 'Audio code map', text);
      speakChunked(data.speech || text);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message || 'Python code map failed.', true);
    }
  }

  async function pythonStepNarration() {
    activateTab('python');
    if (!requirePythonCode()) return;
    const token = startHeartbeat('Narrating Python steps');
    try {
      const data = await apiJsonLoose('/python/step-narration', {
        method: 'POST',
        body: JSON.stringify(pythonPayload()),
      });
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      const lines = data.narration || [];
      const text = lines.length ? lines.join('\n') : (data.narration_text || data.speech || '');
      state.lastStepNarration = text;
      writeOutput(text || 'No Python steps returned.', false);
      recordPythonHistory('step-narration', 'Step narration', text || 'No Python steps returned.');
      speakChunked(data.speech || data.narration_text || text);
      if (!data.success && data.error) state.lastPythonError = data.error;
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message || 'Python step narration failed.', true);
    }
  }

  function formatPythonStateWatch(data) {
    const step = data.step || {};
    const lines = [
      'PYTHON STEP WATCH',
      data.explanation || data.speech || '',
      '',
      `Step ${(data.cursor || 0) + 1} of ${data.total_steps || 0}`,
    ];
    if (step.line) lines.push(`Line ${step.line}: ${step.source || ''}`);
    if (step.changed_variables && step.changed_variables.length) {
      lines.push('Changed variables:');
      step.changed_variables.forEach((change) => {
        const oldValue = change.old === null || change.old === undefined ? '(not set)' : change.old;
        lines.push(`- ${change.name}: ${oldValue} -> ${change.new}`);
      });
    }
    if (step.output) lines.push(`Output at this step: ${step.output}`);
    if (step.loop_context) {
      const loop = step.loop_context;
      const target = loop.target && loop.target_value ? `, ${loop.target} is ${loop.target_value}` : '';
      lines.push(`Loop context: line ${loop.line}, iteration ${loop.iteration}${target}.`);
    }
    if (step.function_call) {
      const call = step.function_call;
      const params = (call.parameters || []).map((item) => `${item.name}=${item.value}`).join(', ');
      lines.push(`Function call: ${call.function} from line ${call.call_line || '?'}${params ? ` with ${params}` : ''}.`);
    }
    if (step.function_context) {
      lines.push(`Function context: ${step.function_context}.`);
    }
    if (step.function_locals && Object.keys(step.function_locals).length) {
      lines.push('Function locals:');
      Object.keys(step.function_locals).slice(0, 6).forEach((name) => {
        lines.push(`- ${name}: ${step.function_locals[name]}`);
      });
    }
    if (step.function_return) {
      const returned = step.function_return;
      lines.push(`Function return: ${returned.function} returned ${returned.return_value}.`);
    }
    if (step.condition) {
      lines.push(`Condition: ${step.condition.expression} was ${step.condition.result ? 'true' : 'false'}.`);
    }
    return lines.filter(Boolean).join('\n');
  }

  async function pythonStateWatch(action = 'current', command = '', slots = {}) {
    activateTab('python');
    if (!requirePythonCode()) return;
    const stateAction = slots.state_action || action || 'current';
    const variable = slots.variable || pythonVariableFromCommand(command, slots);
    const currentCode = getPython();
    const currentInputs = JSON.stringify(getPythonInputs());
    const stateKey = `${currentCode}\n::inputs::${currentInputs}`;
    const cursor = state.lastPythonStateKey === stateKey ? (state.lastPythonStepCursor || 0) : 0;
    const token = startHeartbeat('Reading Python step');
    try {
      const data = await apiJsonLoose('/python/state-watch', {
        method: 'POST',
        body: JSON.stringify(pythonPayload({
          action: stateAction,
          cursor,
          variable,
        })),
      });
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      state.lastPythonStateWatch = data;
      state.lastPythonStateKey = stateKey;
      state.lastPythonStepCursor = data.cursor || 0;
      const text = formatPythonStateWatch(data);
      writeOutput(text, false);
      recordPythonHistory('state-watch', 'Step watch', data.explanation || text);
      speak(data.speech || data.explanation || text);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message || 'Python step watch failed.', true);
    }
  }

  function pythonVariableFromCommand(command, slots = {}) {
    if (slots.variable) return String(slots.variable);
    const match = String(command || '').match(/\b(?:watch|track|show|read|explain)\s+(?:the\s+)?(?:python\s+)?(?:variable\s+)?([A-Za-z_]\w*)\b/i)
      || String(command || '').match(/\bvariable\s+([A-Za-z_]\w*)\b/i);
    return match ? match[1] : '';
  }

  async function pythonWatchVariable(command = '', slots = {}) {
    activateTab('python');
    const variable = pythonVariableFromCommand(command, slots);
    const token = startHeartbeat(variable ? `Watching ${variable}` : 'Reading Python state');
    try {
      const data = await apiJsonLoose('/python/watch-variable', {
        method: 'POST',
        body: JSON.stringify(pythonPayload(variable ? { action: 'add', variable } : { action: 'check' })),
      });
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      const stateLines = data.state
        ? Object.keys(data.state).map((name) => `${name}: ${data.state[name].value}`)
        : [];
      const text = [data.speech || '', stateLines.length ? '\nVariables:\n' + stateLines.join('\n') : '']
        .join('')
        .trim();
      writeOutput(text || 'No Python variable state returned.', false);
      recordPythonHistory('variable-watch', 'Variable watch', text || 'No Python variable state returned.');
      speak(data.speech || text);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message || 'Python variable watch failed.', true);
    }
  }

  function pythonBreakpointCondition(command = '', slots = {}) {
    if (slots.condition) return String(slots.condition).trim();
    const field = $('pythonBreakpointInput');
    if (field && field.value.trim() && !command) return field.value.trim();
    const cleaned = String(command || '')
      .replace(/^(?:please\s+)?(?:break|pause|stop|alert\s+me|tell\s+me|conditional\s+breakpoint|breakpoint)(?:\s+execution)?\s+(?:when\s+)?/i, '')
      .trim();
    return cleaned || (field ? field.value.trim() : '');
  }

  async function pythonConditionalBreakpoint(command = '', slots = {}) {
    activateTab('python');
    if (!requirePythonCode()) return;
    const condition = pythonBreakpointCondition(command, slots);
    if (!condition) {
      writeOutput('Type a condition first, like total > 10 or name == "Amit".', true);
      return;
    }
    const field = $('pythonBreakpointInput');
    if (field && !field.value.trim()) field.value = condition;
    const token = startHeartbeat('Checking Python breakpoint');
    try {
      const data = await apiJsonLoose('/python/conditional-breakpoint', {
        method: 'POST',
        body: JSON.stringify(pythonPayload({ action: 'add', condition })),
      });
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      const text = data.explanation || data.speech || (data.triggered ? 'Conditional audio breakpoint hit.' : 'No breakpoint was hit.');
      const visible = [
        data.triggered ? 'CONDITIONAL AUDIO BREAKPOINT HIT' : 'CONDITIONAL AUDIO BREAKPOINT',
        text,
        data.output ? `\nProgram output:\n${String(data.output).trim()}` : '',
      ].filter(Boolean).join('\n');
      writeOutput(visible, false);
      recordPythonHistory('breakpoint', data.triggered ? 'Breakpoint hit' : 'Breakpoint checked', visible);
      speakChunked(data.speech || text);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      stopHeartbeat(token);
      writeOutput(error.message || 'Conditional breakpoint failed.', true);
    }
  }

  async function pythonExplainError() {
    activateTab('python');
    const error = state.lastPythonError || ((state.lastPythonRun || {}).error || '');
    if (!error) {
      writeOutput('There is no recent Python error. Run the Python code first.', true);
      return;
    }
    try {
      const data = await apiJsonLoose('/python/explain-error', {
        method: 'POST',
        body: JSON.stringify(pythonPayload({ error })),
      });
      const text = data.reply || data.speech || error;
      writeOutput(text, false);
      speakChunked(data.speech || text);
    } catch (err) {
      writeOutput(err.message || 'Python error explanation failed.', true);
    }
  }

  async function pythonMistakeReplay() {
    activateTab('python');
    try {
      const data = await apiJsonLoose('/python/mistake-replay', {
        method: 'POST',
        body: JSON.stringify(pythonPayload()),
      });
      const text = data.reply || data.speech || 'No Python mistake replay returned.';
      writeOutput(text, false);
      recordPythonHistory('mistake-replay', 'Mistake replay', text);
      speakChunked(data.speech || text);
    } catch (error) {
      writeOutput(error.message || 'Python mistake replay failed.', true);
    }
  }

  async function stepNarration() {
    if (state.activeTab === 'python') return pythonStepNarration();
    return projectText('/project-step-narration', 'lastStepNarration', 'Building step narration');
  }

  async function explainProjectFile(target = '') {
    let file = target || state.activeTab || 'html';
    const lower = String(file).toLowerCase();
    if (lower.includes('css') || lower.includes('style')) file = 'style.css';
    else if (lower.includes('javascript') || lower.includes('java script') || /\bjs\b/.test(lower) || lower.includes('script')) file = 'script.js';
    else file = 'index.html';
    if (file === 'style.css') activateTab('css');
    else if (file === 'script.js') activateTab('js');
    else activateTab('html');
    return projectText('/project-file-explanation', 'lastFileExplanation', `Explaining ${file}`, { file });
  }

  async function learningNotes() {
    return projectText('/project-learning-notes', 'lastLearningNotes', 'Building learning notes');
  }

  async function accessibilityMap() {
    return projectText('/project-accessibility-map', 'lastAccessibilityMap', 'Building accessibility map');
  }

  async function reviewProject() {
    return projectText('/project-review', 'lastProjectReview', 'Reviewing project');
  }

  async function describePreview() {
    return projectText('/preview-description', 'lastPreviewDescription', 'Describing preview');
  }

  async function projectSummary() {
    return projectText('/project-summary', 'lastProjectSummary', 'Building project summary');
  }
  async function landmarks() {
    return projectText('/project-landmarks', 'lastLandmarks', 'Listing page landmarks');
  }

  async function trainerNotes() {
    return projectText('/trainer-notes', 'lastTrainerNotes', 'Writing trainer notes');
  }

  async function studentRecap() {
    return projectText('/student-recap', 'lastStudentRecap', 'Building your learning recap', {
      commands: (state.commandHistory || []).slice(-12),
    });
  }

  async function screenReaderSummary() {
    return projectText('/screen-reader-summary', 'lastScreenReaderSummary', 'Preparing screen reader summary');
  }
  async function runWebsite() {
    const text = await projectText('/website-runtime-teacher', 'lastRunSummary', 'Reading your website');
    if (text) suggestNext(['what CSS affects the main button', 'debug website', 'is this ready to share']);
    return text;
  }

  async function debugWebsite() {
    const text = await projectText('/website-debug-teacher', 'lastDebugReport', 'Debugging your website');
    if (text) suggestNext(['fix website error', 'run website', 'check javascript connections']);
    return text;
  }

  async function selectorExplainer(command) {
    const text = await projectText('/selector-explainer', 'lastSelectorExplainer', 'Tracing the CSS', { query: command || '' });
    if (text) suggestNext(['find unused CSS', 'describe the design', 'run website']);
    return text;
  }

  async function pilotReport() {
    const text = await projectText('/pilot-report', 'lastPilotReport', 'Writing the pilot report', {
      commands: (state.commandHistory || []).slice(-20),
      versions: (state.versions || []).slice(-10).map((v) => ({
        label: v.note || v.label, command: v.command || '', summary: v.summary || [],
      })),
    });
    if (text) suggestNext(['export website', 'is this ready to share', 'trainer notes']);
    return text;
  }

  async function screenReaderTour() {
    return projectText('/screen-reader-tour', 'lastScreenReaderTour', 'Building the screen reader tour');
  }

  async function keyboardTest() {
    return projectText('/keyboard-test', 'lastKeyboardTest', 'Testing keyboard navigation');
  }

  async function visualDescription() {
    return projectText('/visual-description', 'lastVisualDescription', 'Describing the design');
  }

  async function readinessScore() {
    const text = await projectText('/accessibility-readiness-score', 'lastReadinessScore', 'Scoring readiness');
    if (text) suggestNext(['fix accessibility issues', 'make pilot report', 'export website']);
    return text;
  }

  async function teacherReview() {
    const token = nextAsyncToken();
    writeOutput('Reviewing like a teacher...');
    try {
      const data = await apiJson('/teacher-review', { method: 'POST', body: JSON.stringify(projectPayload()) });
      if (!isAsyncFresh(token)) return '';
      state.lastTeacherReview = data.text || '';
      state.teacherSuggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
      writeOutput(state.lastTeacherReview, false);
      speakChunked(state.lastTeacherReview);
      suggestNext(['check accessibility', 'screen reader tour', 'test keyboard navigation']);
      return state.lastTeacherReview;
    } catch (error) {
      if (!isAsyncFresh(token)) return '';
      writeOutput(error.message || 'Teacher review failed.', true);
      return '';
    }
  }

  async function debugFix() {
    const token = nextAsyncToken();
    writeOutput('Applying safe website fixes...');
    beginReplay('Before debug fix');
    try {
      const data = await apiJson('/debug-fix', {
        method: 'POST',
        body: JSON.stringify({ html: getHtmlSource(), css: getCss(), js: getJs() }),
      });
      if (!isAsyncFresh(token)) return;
      if (data.changed && data.html) {
        snapshotVersion('Before debug fix');
        loadGeneratedFiles({ html: data.html, css: data.css, js: data.js });
        snapshotVersion('Applied debug fix', data.summary || []);
        finishReplay('After debug fix');
        try { await publish(getHtml()); } catch (error) {}
      }
      writeOutput(data.message || (data.summary || []).join('\n') || 'No safe fix was available.', true);
      suggestNext(['run website', 'debug this website', 'replay change']);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      writeOutput(error.message || 'Debug fix failed.', true);
    }
  }
  function showHistory() {
    const versions = state.versions || [];
    if (!versions.length) {
      writeOutput('No saved versions yet. Generate or edit a website first.', true);
      return true;
    }
    const recent = versions.slice(-10);
    const lines = ['VERSION HISTORY', '', `You have ${recent.length} saved version(s) (most recent last):`];
    recent.forEach((version, index) => {
      const command = version.command ? ` â€” command: "${version.command}"` : '';
      const summary = (version.summary && version.summary.length) ? ` (${version.summary.join('; ')})` : '';
      lines.push(`${index + 1}. ${version.note || version.label || 'Saved version'}${command}${summary}`);
    });
    lines.push('', 'Say "undo last change" to step back, or "compare versions" to hear what changed.');
    writeOutput(lines.join('\n'), true);
    suggestNext(['undo last change', 'compare versions', 'replay change']);
    return true;
  }
  function normalizeTrack(token) {
    const lowered = (token || '').toLowerCase();
    if (lowered === 'js') return 'javascript';
    if (lowered === 'form') return 'forms';
    return lowered;
  }

  async function loadTutorialTracks() {
    if (state.tracks) return state.tracks;
    try {
      const data = await apiJson('/tutorial/tracks', { method: 'GET' });
      state.tracks = data.tracks || {};
    } catch (error) {
      state.tracks = {};
    }
    return state.tracks;
  }

  function trackStepMessage() {
    const track = state.track;
    const step = track.steps[track.index];
    if (!step) return `Tutorial complete. You finished the ${track.title}. Say "exit tutorial" or keep building.`;
    return (
      `${track.title} â€” step ${track.index + 1} of ${track.steps.length}: ${step.title}. ${step.say} ` +
      `Try: "${step.command}". Say "next", "repeat", or "exit tutorial".`
    );
  }

  function persistTrackState() {
    if (!state.track || !state.track.id) return;
    saveJsonStore('codeup_track_state', {
      active: !!state.track.active,
      guided: !!state.track.guided,
      id: state.track.id,
      index: state.track.index || 0,
      steps: Array.isArray(state.track.steps) ? state.track.steps : [],
      title: state.track.title || 'Tutorial',
    });
  }

  function clearTrackState() {
    try { localStorage.removeItem('codeup_track_state'); } catch (error) {}
  }
  async function startTrack(trackId) {
    const tracks = await loadTutorialTracks();
    const track = tracks[trackId];
    if (!track) { writeOutput('That tutorial track is not available yet. Try "start HTML tutorial."', true); return true; }
    state.track = { active: true, id: trackId, index: 0, steps: track.steps || [], title: track.title || 'Tutorial' };
    state.tutorial.active = false;
    persistTrackState();
    const msg = trackStepMessage();
    updateTutorialPanel(msg);
    writeOutput(msg, true);
    return true;
  }

  function trackNext() {
    if (!state.track.active) return false;
    if (state.track.index < state.track.steps.length) state.track.index += 1;
    const msg = trackStepMessage();
    updateTutorialPanel(msg);
    writeOutput(msg, true);
    if (state.track.index >= state.track.steps.length) state.track.active = false;
    persistTrackState();
    return true;
  }

  function trackRepeat() {
    if (!state.track.active) return false;
    const msg = trackStepMessage();
    updateTutorialPanel(msg);
    writeOutput(msg, true);
    return true;
  }

  function trackExit() {
    state.track.active = false;
    clearTrackState();
    updateTutorialPanel('Tutorial paused. Type "start HTML tutorial" or "start tutorial" to resume.');
    writeOutput('Tutorial paused. You are back in normal building mode.', true);
    return true;
  }

  function trackHint() {
    if (!state.track.active) return false;
    const step = state.track.steps[state.track.index];
    const msg = step ? `Hint: ${step.hint || step.say || ('Try: ' + step.command)}` : 'No hint available.';
    updateTutorialPanel(msg);
    writeOutput(msg, true);
    return true;
  }

  async function trackRecap() {
    if (!state.track.active) return false;
    if (state.track.guided) {
      const text = await projectText('/guided-build/recap', 'lastGuidedRecap', 'Recapping your progress');
      return !!text || true;
    }
    const done = state.track.index;
    const msg = `Recap: you are on step ${state.track.index + 1} of ${state.track.steps.length} in the ${state.track.title}. ${done} step(s) behind you.`;
    updateTutorialPanel(msg);
    writeOutput(msg, true);
    return true;
  }
  async function loadGuidedSteps() {
    if (state.guidedSteps) return state.guidedSteps;
    try {
      const data = await apiJson('/guided-build/steps', { method: 'GET' });
      state.guidedSteps = data.steps || [];
    } catch (error) {
      state.guidedSteps = [];
    }
    return state.guidedSteps;
  }

  async function startGuidedBuild() {
    const steps = await loadGuidedSteps();
    if (!steps.length) { writeOutput('The guided build track is not available right now.', true); return true; }
    state.track = { active: true, guided: true, id: 'first_website', index: 0, steps, title: 'Build your first website by ear' };
    persistTrackState();
    state.tutorial.active = false;
    const intro = 'Guided build. We will make a website step by step, by ear. Say "next" to move on, "repeat" to hear the step, "hint" for help, "recap" for progress, or "exit tutorial" to stop.';
    const msg = `${intro}\n\n${trackStepMessage()}`;
    updateTutorialPanel(msg);
    writeOutput(msg, true);
    return true;
  }

  async function loadGuidedProjects() {
    if (Array.isArray(state.guidedProjects)) return state.guidedProjects;
    try {
      const data = await apiJson('/guided-projects', { method: 'GET' });
      state.guidedProjects = Array.isArray(data.projects) ? data.projects : [];
    } catch (error) {
      state.guidedProjects = [];
    }
    return state.guidedProjects;
  }

  function guidedProjectLine(project, index) {
    const skills = Array.isArray(project.skills) ? project.skills.join(', ') : 'starter skills';
    return `${index + 1}. ${project.title} (${project.slug})\n   Goal: ${project.goal}\n   Skills: ${skills}\n   Start: start guided project ${project.slug}`;
  }

  async function showGuidedProjects() {
    const projects = await loadGuidedProjects();
    if (!projects.length) {
      writeOutput('No guided project starters are available right now.', true);
      return true;
    }
    const lines = [
      'GUIDED PROJECT STARTERS',
      '',
      'These are starter projects. Each one generates editable HTML, CSS, and JavaScript in Monaco, then uses preview, audit, debug, and export checks for review.',
      '',
      ...projects.map(guidedProjectLine),
    ];
    writeOutput(lines.join('\n'), true);
    suggestNext(projects.slice(0, 3).map(project => `start guided project ${project.slug}`));
    return true;
  }

  async function startGuidedProject(command) {
    const projects = await loadGuidedProjects();
    const requested = command.replace(/^(start|open|begin|build)\s+(a\s+|the\s+)?guided\s+project\s*/i, '').trim().toLowerCase();
    const project = projects.find(item => {
      const haystack = `${item.slug || ''} ${item.title || ''}`.toLowerCase();
      return haystack.includes(requested) || requested.includes(item.slug || '') || requested.includes((item.title || '').toLowerCase());
    }) || projects[0];
    if (!project) {
      writeOutput('No guided project starters are available right now.', true);
      return true;
    }
    state.guidedProject = {
      slug: project.slug,
      title: project.title,
      status: 'in_progress',
      startedAt: new Date().toISOString(),
      starterPrompt: project.starter_prompt,
    };
    saveJsonStore('codeup_guided_project', state.guidedProject);
    snapshotVersion(`Checkpoint before guided project: ${project.title}`, [`Started guided project starter ${project.slug}.`]);
    writeOutput(`Starting guided project: ${project.title}.\n\nGoal: ${project.goal}\n\nI will generate the starter now. Use preview, audit, debug, and export to verify it as you build.`, true);
    await buildWebsite(project.starter_prompt || project.title || 'guided project starter', true);
    return true;
  }
  async function validateGuidedProgress() {
    const track = state.track;
    if (!track || !track.active || !track.guided) return;
    const step = track.steps[track.index];
    if (!step) return;
    try {
      const data = await apiJson('/guided-build/validate', {
        method: 'POST',
        body: JSON.stringify(projectPayload({ step: step.id })),
      });
      updateTutorialPanel(data.message);
    } catch (error) { }
  }

  function explainJs() {
    const map = buildCodeMap();
    if (!map.fns.length && !map.events.length) {
      writeOutput(t('There is no JavaScript yet. Generate a website or add interactivity first.', 'Abhi JavaScript nahi hai.'), true);
      return;
    }
    const msg = t(
      `The JavaScript defines ${map.fns.length} function${map.fns.length === 1 ? '' : 's'}: ${map.fns.join(', ') || 'none'}. It listens for these events: ${map.events.join(', ') || 'none'}.`,
      `JavaScript mein ${map.fns.length} functions hain: ${map.fns.join(', ') || 'none'}. Yeh events sunta hai: ${map.events.join(', ') || 'none'}.`
    );
    writeOutput(msg, true);
  }
  async function analyzeCode() {
    const token = nextAsyncToken();
    writeOutput(t('Analyzing the code...', 'Code analyze ho raha hai...'));
    try {
      const response = await fetch('/html-audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html: getHtml(), project_id: state.projectId }),
      });
      const data = await response.json();
      if (!data.success) throw new Error(data.error || 'Analyze failed.');
      if (!isAsyncFresh(token)) return;
      const audit = data.audit;
      state.lastAudit = audit;
      const issues = audit.issues || [];
      const fixable = issues.filter((item) => item.autofix);
      const one = $('auditFixOneBtn');
      const all = $('auditFixAllBtn');
      if (one) one.disabled = fixable.length === 0;
      if (all) all.disabled = fixable.length === 0;

      const checks = audit.checks.map((item) => `${item.passed ? 'PASS' : 'FIX '} - ${item.label}`).join('\n');
      const issueLines = issues
        .map((item) => `${item.severity.toUpperCase()} - ${item.id}: ${item.description}\n  Fix: ${item.suggested_fix}`)
        .join('\n');
      const jsNote = analyzeJsSyntax();
      const detail = `Analysis â€” accessibility score ${audit.score}/100\n\n${checks}\n\n` +
        `Issues:\n${issueLines || 'No structured issues found.'}\n\n` +
        `JavaScript: ${jsNote.message}\n\n` +
        `Suggestions:\n${audit.suggestions.map((s) => '- ' + s).join('\n')}`;
      writeOutput(detail, false);

      const top = issues.slice(0, 3).map((item) => item.id.replace(/_/g, ' ')).join(', ');
      const jsSpoken = jsNote.ok ? '' : ' ' + jsNote.message;
      const spoken = issues.length
        ? t(
            `Analysis done. Accessibility score ${audit.score} out of 100. ${issues.length} issue${issues.length === 1 ? '' : 's'} found: ${top}. Press Fix to repair the safe ones.${jsSpoken}`,
            `Analysis ho gaya. Score ${audit.score}. ${issues.length} issues mile: ${top}. Fix dabaiye.${jsSpoken}`
          )
        : t(
            `Analysis done. Accessibility score ${audit.score} out of 100. No structured issues found.${jsSpoken}`,
            `Analysis ho gaya. Score ${audit.score}. Koi structured issue nahi mila.${jsSpoken}`
          );
      speak(spoken);
    } catch (error) {
      if (!isAsyncFresh(token)) return;
      writeOutput(error.message, true);
    }
  }
  function analyzeJsSyntax() {
    const js = getJs() || (getHtmlSource().match(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/i) || [])[1] || '';
    if (!js.trim()) return { ok: true, message: 'No JavaScript yet.' };
    const noStrings = js
      .replace(/\/\/[^\n]*/g, '')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/'(?:\\.|[^'\\])*'/g, "''")
      .replace(/"(?:\\.|[^"\\])*"/g, '""')
      .replace(/`(?:\\.|[^`\\])*`/g, '``');
    const pairs = { ')': '(', ']': '[', '}': '{' };
    const stack = [];
    for (const ch of noStrings) {
      if (ch === '(' || ch === '[' || ch === '{') stack.push(ch);
      else if (pairs[ch]) {
        if (stack.pop() !== pairs[ch]) return { ok: false, message: 'Possible JavaScript syntax issue: unbalanced brackets.' };
      }
    }
    if (stack.length) return { ok: false, message: 'Possible JavaScript syntax issue: unclosed bracket.' };
    return { ok: true, message: 'No obvious syntax problems.' };
  }
  function stopEverything() {
    nextAsyncToken();
    cancelSpeech();
    stopHeartbeat();
    if (_sonifyTimer) { clearTimeout(_sonifyTimer); _sonifyTimer = null; }
    if (window.VoiceMemoryEngine && typeof window.VoiceMemoryEngine.interrupt === 'function') {
      try { window.VoiceMemoryEngine.interrupt(); } catch (error) {}
    }
    updateStateIndicator('IDLE');
    announce(t('Stopped.', 'Ruk gaya.'));
    const output = $('output');
    if (output) output.textContent = t('Stopped speaking.', 'Bolna band ho gaya.');
  }
  function applyDesignPreset(name) {
    const presets = {
      futuristic: [
        ':root { --old-futuristic-preset-color: #05060f; }',
        'body { background: #f8fafc; color: #111827; }',
        'header, .hero { background: #e0f2fe; color: #111827; border-bottom: 1px solid #93c5fd; }',
        'section, article, .card { background: #ffffff; border: 1px solid #cbd5e1; color: #111827; }',
        'a, button, .button { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }',
      ],
      vibrant: [
        'header, .hero { background: #fff7ed; color: #111827; border-bottom: 1px solid #fb923c; }',
        'section, article, .card { border-left: 4px solid #2563eb; }',
        'a, button, .button { background: #2563eb; color: #ffffff; border: 1px solid #1d4ed8; }',
      ],
      animated: [
        'section, article, .card { border: 1px solid #cbd5e1; }',
        'a:hover, button:hover, .button:hover { text-decoration: underline; }',
      ],
    };
    const rules = presets[name];
    if (!rules) return false;
    snapshotVersion('Before design preset');
    beginReplay('Before design preset');
    appendCssRules(rules);
    finishReplay('After design preset');
    snapshotVersion('Applied design preset', [`Applied ${name} design rules.`]);
    writeOutput(t(`Applied a ${name} design.`, `${name} design apply ho gaya.`), true);
    previewHtml(false, { silent: true });
    return true;
  }
  function addContactSection() {
    snapshotVersion('Before adding contact section');
    beginReplay('Before adding contact section');
    const block = '\n<section id="contact" aria-labelledby="contact-heading">\n' +
      '  <h2 id="contact-heading">Contact Us</h2>\n' +
      '  <p>Have a question? Send us a message.</p>\n' +
      '  <form data-contact-form novalidate>\n' +
      '    <label for="contact-name">Your name</label>\n' +
      '    <input id="contact-name" name="name" type="text" required>\n' +
      '    <label for="contact-email">Email address</label>\n' +
      '    <input id="contact-email" name="email" type="email" required>\n' +
      '    <label for="contact-message">Message</label>\n' +
      '    <textarea id="contact-message" name="message" rows="4" required></textarea>\n' +
      '    <button type="submit">Send message</button>\n' +
      '  </form>\n' +
      '</section>\n';
    activateTab('html');
    insertAtCursor(block);
    state.pages[state.currentPage] = getHtml();
    finishReplay('After adding contact section');
    writeOutput(t('Added a contact section with an accessible form.', 'Accessible form ke saath contact section add ho gaya.'), true);
    previewHtml(false, { silent: true });
    return true;
  }
  function refreshSnippetSelect() {
    const select = $('snippetSelect');
    if (!select) return;
    const snippets = loadSnippets();
    const names = Object.keys(snippets);
    select.innerHTML = '';
    if (!names.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = t('No snippets yet', 'Abhi koi snippet nahi');
      select.appendChild(opt);
      return;
    }
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = t('Choose a snippetâ€¦', 'Snippet chuniyeâ€¦');
    select.appendChild(placeholder);
    names.forEach((name) => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      select.appendChild(opt);
    });
  }

  function saveSnippetFromUi() {
    const input = $('snippetNameInput');
    const name = input ? input.value.trim() : '';
    saveSnippet(name || ('snippet ' + (Object.keys(loadSnippets()).length + 1)));
    refreshSnippetSelect();
  }

  function loadSnippetFromUi() {
    const select = $('snippetSelect');
    const name = select ? select.value : '';
    if (!name) { writeOutput(t('Choose a snippet to load first.', 'Pehle ek snippet chuniye.'), true); return; }
    loadSnippet(name);
    previewHtml(false, { silent: true });
  }

  function deleteSnippetFromUi() {
    const select = $('snippetSelect');
    const name = select ? select.value : '';
    if (!name) { writeOutput(t('Choose a snippet to delete first.', 'Pehle ek snippet chuniye.'), true); return; }
    deleteSnippet(name);
    refreshSnippetSelect();
  }
  const COMMAND_PHRASE_REPAIRS = [
    [/\bexport\s+side\b/gi, 'export site'],
    [/\bmake\s+webside\b/gi, 'make website'],
  ];
  const COMMAND_TOKEN_REPAIRS = {
    webside: 'website', wesbite: 'website', websit: 'website', wbsite: 'website',
    accessiblity: 'accessibility', accesibility: 'accessibility', accessibilty: 'accessibility', acessibility: 'accessibility',
    explane: 'explain', explian: 'explain',
    profeshnal: 'professional', profesional: 'professional', professionl: 'professional',
    cantact: 'contact', conatct: 'contact',
    naration: 'narration', nardation: 'narration',
    mapp: 'map',
  };
  const COMMAND_TOKEN_RE = new RegExp('\\b(' + Object.keys(COMMAND_TOKEN_REPAIRS).join('|') + ')\\b', 'gi');

  function repairCommand(text) {
    if (!text) return text;
    let repaired = text;
    COMMAND_PHRASE_REPAIRS.forEach(([pattern, replacement]) => { repaired = repaired.replace(pattern, replacement); });
    repaired = repaired.replace(COMMAND_TOKEN_RE, (match) => COMMAND_TOKEN_REPAIRS[match.toLowerCase()] || match);
    return repaired;
  }

  function recordCommand(text) {
    const clean = (text || '').trim();
    if (!clean) return;
    state.commandHistory = state.commandHistory || [];
    if (state.commandHistory[state.commandHistory.length - 1] === clean) return;
    state.commandHistory.push(clean);
    if (state.commandHistory.length > 40) state.commandHistory.shift();
  }

  function isPythonStateWatchCommand(lower) {
    return /^(next|previous|first|last)\s+step$/.test(lower)
      || /^go\s+back\s+one\s+step$/.test(lower)
      || /^back\s+one\s+step$/.test(lower)
      || /^explain\s+(this|current|the)\s+step$/.test(lower)
      || /^what\s+changed$/.test(lower)
      || /^where\s+am\s+i$/.test(lower)
      || /^repeat\s+(that|this\s+step|step)$/.test(lower)
      || /^why\s+did\s+[A-Za-z_]\w*\s+change$/.test(lower)
      || /^why\s+did\s+(the\s+)?condition\s+(pass|fail)$/.test(lower)
      || /^explain\s+(the\s+)?loop$/.test(lower)
      || /^step\s+into(\s+function)?$/.test(lower)
      || /^step\s+out(\s+of\s+function)?$/.test(lower)
      || /^leave\s+function$/.test(lower)
      || /^what\s+function\s+am\s+i\s+in\??$/.test(lower)
      || /^what\s+arguments\s+were\s+passed\??$/.test(lower)
      || /^what\s+are\s+the\s+parameters\??$/.test(lower)
      || /^what\s+did\s+(it|this\s+function)\s+return\??$/.test(lower)
      || /^where\s+does\s+it\s+go\s+back\??$/.test(lower)
      || /^explain\s+this\s+function(\s+call)?$/.test(lower)
      || /^why\s+did\s+(this\s+)?function\s+return(\s+this)?$/.test(lower);
  }

  function shouldUsePythonStateWatch(lower) {
    if (!isPythonStateWatchCommand(lower)) return false;
    if (state.activeTab === 'python') return true;
    return /\bpython\b|function|condition|variable|loop|argument|parameter|return/.test(lower);
  }
  function handleIdeCommand(command, lower) {
    if (lower === 'help' || lower === 'what can i do here' || lower === 'what can i do here?'
        || lower.includes('what can codeup web do') || lower.includes('show examples')) {
      writeOutput(helpText(), true);
      return true;
    }
    if (lower === 'say more' || lower === 'continue explanation' || lower === 'more explanation') { return speakMore(); }
    if (lower === 'python lab' || lower === 'open python' || lower === 'python editor') { activateTab('python'); writeOutput('Python editor ready.', true); return true; }
    const pythonExampleMatch = lower.match(/^(load|use|open|replace\s+with)\s+(?:the\s+)?(?:python\s+)?(variables?|loop|input|function|condition)\s+example$/);
    if (pythonExampleMatch) {
      const key = pythonExampleMatch[2].startsWith('variable') ? 'variables' : pythonExampleMatch[2];
      return loadPythonExample(key, pythonExampleMatch[1].startsWith('replace'));
    }
    if (lower === 'python history' || lower === 'show python history' || lower === 'review python history') { return showPythonHistory(); }
    if (lower === 'clear python history') { return clearPythonHistory(); }
    if (/^clear\s+(python\s+)?inputs?$/.test(lower)) { return clearPythonInputs(true); }
    if (/^run\s+(python\s+)?with\s+inputs?$/.test(lower)) { runPythonWithInputs(); return true; }
    if (/^(?:add|queue)\s+(?:python\s+)?input\s+/.test(lower)) {
      const value = command.replace(/^(?:add|queue)\s+(?:python\s+)?input\s+/i, '');
      return addPythonInputValue(value, true);
    }
    if (/^(?:break|pause|stop)(?:\s+execution)?\s+when\s+[A-Za-z_]\w*/.test(lower) || /^alert\s+me\s+when\s+[A-Za-z_]\w*/.test(lower) || /^conditional\s+breakpoint\s+[A-Za-z_]\w*/.test(lower) || /^breakpoint\s+when\s+[A-Za-z_]\w*/.test(lower)) { pythonConditionalBreakpoint(command); return true; }
    if (shouldUsePythonStateWatch(lower)) {
      const routed = { state_action: 'current' };
      if (/^next/.test(lower)) routed.state_action = 'next';
      else if (/^(previous|go back|back)/.test(lower)) routed.state_action = 'previous';
      else if (/^first/.test(lower)) routed.state_action = 'first';
      else if (/^last/.test(lower)) routed.state_action = 'last';
      else if (/^what changed/.test(lower)) routed.state_action = 'what_changed';
      else if (/^where am i/.test(lower)) routed.state_action = 'where';
      else if (/^repeat/.test(lower)) routed.state_action = 'repeat';
      else if (/^why did [A-Za-z_]\w* change/i.test(command)) routed.state_action = 'why_variable_change';
      else if (/condition\s+pass/.test(lower)) routed.state_action = 'condition_pass';
      else if (/condition\s+fail/.test(lower)) routed.state_action = 'condition_fail';
      else if (/^explain\s+(the\s+)?loop/.test(lower)) routed.state_action = 'loop';
      else if (/^step\s+into/.test(lower)) routed.state_action = 'step_into';
      else if (/^step\s+out/.test(lower) || /^leave\s+function/.test(lower)) routed.state_action = 'step_out';
      else if (/^what\s+function\s+am\s+i\s+in/.test(lower)) routed.state_action = 'where_function';
      else if (/^explain\s+this\s+function/.test(lower)) routed.state_action = 'function';
      else if (/^what\s+arguments/.test(lower)) routed.state_action = 'arguments';
      else if (/^what\s+are\s+the\s+parameters/.test(lower)) routed.state_action = 'parameters';
      else if (/^what\s+did\s+(it|this\s+function)\s+return/.test(lower)) routed.state_action = 'return';
      else if (/^where\s+does\s+it\s+go\s+back/.test(lower)) routed.state_action = 'go_back';
      else if (/^why\s+did\s+(this\s+)?function\s+return/.test(lower)) routed.state_action = 'why_function_return';
      const variableMatch = command.match(/^why\s+did\s+([A-Za-z_]\w*)\s+change/i);
      if (variableMatch) routed.variable = variableMatch[1];
      pythonStateWatch(routed.state_action, command, routed);
      return true;
    }
    if (/\brun\s+(my\s+)?python(\s+code)?\b/.test(lower) || /\brun\s+(this\s+)?(python\s+)?program\b/.test(lower) || /\brun\s+(this\s+)?code\b/.test(lower)) { runPythonCode(); return true; }
    if (/\bteach\s+me\s+this\s+code\b/.test(lower) || /\bteach\s+me\s+this\s+python\b/.test(lower) || /\bexplain\s+this\s+python\s+code\b/.test(lower) || /\bexplain\s+this\s+program\b/.test(lower)) { analyzePythonCode('teach'); return true; }
    if (/\banaly[sz]e\s+(this\s+)?python(\s+code)?\b/.test(lower) || /\banaly[sz]e\s+this\s+code\b/.test(lower) || /\banaly[sz]e\s+(this\s+)?program\b/.test(lower)) { analyzePythonCode('analyze'); return true; }
    if (/\b(audio|python)\s+code\s+map\b/.test(lower) || /\bmap\s+this\s+python\b/.test(lower) || /\bexplain\s+python\s+structure\b/.test(lower)) { pythonAudioCodeMap(command); return true; }
    if (/\bstep\s+through\s+(this\s+)?(python|code)\b/.test(lower) || /\bnarrate\s+python\s+execution\b/.test(lower) || /\bspoken\s+debug/.test(lower)) { pythonStepNarration(); return true; }
    if (/\b(variable\s+watch|show\s+program\s+state)\b/.test(lower) || /\b(?:watch|track|show|read|explain)\s+(?:the\s+)?(?:python\s+)?variable\b/.test(lower)) { pythonWatchVariable(command); return true; }
    if (/\b(explain|read)\s+(the\s+)?python\s+error\b/.test(lower) || /\bwhy\s+did\s+(my\s+)?python\s+crash\b/.test(lower)) { pythonExplainError(); return true; }
    if (/\breplay\s+(my\s+)?python\s+mistake\b/.test(lower) || /\bcompare\s+python\s+before\s+and\s+after\b/.test(lower) || /\bwhy\s+does\s+the\s+python\s+fix\s+work\b/.test(lower)) { pythonMistakeReplay(); return true; }
    if (lower.includes('show guided projects') || lower.includes('list guided projects') || lower === 'guided projects') { showGuidedProjects(); return true; }
    if (/^(start|open|begin|build)\s+(a\s+|the\s+)?guided\s+project\b/.test(lower)) { startGuidedProject(command); return true; }
    if (lower.includes('start web tutorial') || lower.includes('build my first website') || lower.includes('build a website by ear') || lower.includes('guided build')) { startGuidedBuild(); return true; }
    if (handleWebInsertCommand(command, lower)) return true;
    if (/^(add|insert)\s+(a\s+)?button(\s+.+)?$/i.test(command)) { return addHtmlFromSpeech(command); }
    if (lower.includes('where am i') || lower.includes('read breadcrumb') || lower.includes('what am i editing')) { breadcrumb(); return true; }
    if (lower.includes('step narration') || lower.includes('narrate steps') || lower.includes('walk me through') || lower.includes('how this runs') || lower.includes('how does this code work') || lower.includes('teach me this website')) { stepNarration(); return true; }
    if (lower.includes('trainer notes') || lower.includes('teacher notes') || lower.includes('trainer handoff') || lower.includes('lesson notes') || /notes? for (the )?teacher/.test(lower)) { trainerNotes(); return true; }
    if (lower.includes('what did i learn') || lower.includes('session recap') || lower.includes('learning recap')) { studentRecap(); return true; }
    if (lower === 'landmarks' || lower.includes('list landmarks') || lower.includes('website landmarks') || lower.includes('page landmarks') || lower.includes('show landmarks') || lower === 'sections' || lower === 'show sections' || lower.includes('show me the sections') || lower.includes('list sections') || lower.includes('page sections')) { landmarks(); return true; }
    if (/prepare (this )?for nvda/.test(lower) || /prepare (this )?for (a )?screen reader/.test(lower) || lower.includes('screen reader summary') || lower.includes('nvda summary') || lower === 'nvda') { screenReaderSummary(); return true; }
    if (lower.includes('fix website error') || lower.includes('fix javascript error') || lower.includes('fix js error')) { debugFix(); return true; }
    if (lower.includes('debug') || lower.includes('why is this website broken') || lower.includes('why is my button not working') || lower.includes('explain website error') || lower.includes('explain errors') || lower.includes('check console errors') || lower.includes('check javascript connections') || lower.includes('debug this like a teacher')) { debugWebsite(); return true; }
    if (lower.includes('run website') || lower.includes('test website') || lower.includes('run this website') || lower.includes('test this site') || lower.includes('test this website') || lower.includes('check if this website works') || lower.includes('what happens when this runs') || lower.includes('runtime teacher') || lower.includes('teach me how this website runs')) { runWebsite(); return true; }
    if (lower.includes('screen reader tour') || lower.includes('reading order tour') || lower.includes('screen reader reading order') || lower.includes('how would a screen reader read this') || lower.includes('nvda tour') || lower.includes('jaws tour')) { screenReaderTour(); return true; }
    if (lower.includes('test keyboard navigation') || lower.includes('keyboard navigation test') || lower.includes('keyboard test') || lower === 'tab order' || lower.includes('test tab order') || lower.includes('can keyboard users use this') || lower === 'focus order') { keyboardTest(); return true; }
    if (lower.includes('describe the design') || lower.includes('describe the website visually') || lower.includes('what does the website look like') || lower.includes('visual description') || lower.includes('describe layout') || lower.includes('describe colour') || lower.includes('describe color')) { visualDescription(); return true; }
    if (lower.includes('is this ready to share') || lower.includes('website readiness') || lower.includes('readiness score') || lower.includes('readiness check') || lower.includes('nab readiness') || lower.includes('project score') || lower.includes('is this website good') || lower.includes('should i share this') || lower.includes('can i export this') || lower.includes('teacher check')) { readinessScore(); return true; }
    if (lower.includes('what css affects') || lower.includes('which css affects') || lower.includes('explain css for') || lower.includes('unused css') || lower.includes('which html uses')) { selectorExplainer(command); return true; }
    if (lower.includes('pilot report') || lower.includes('trainer report') || lower.includes('summarize this session') || lower.includes('summarise this session') || lower.includes('what did the student learn')) { pilotReport(); return true; }
    if (lower.includes('improve like a teacher') || lower.includes('review like a teacher') || lower.includes('suggest improvements') || lower.includes('teacher review') || lower.includes('improve this project')) { teacherReview(); return true; }
    if (lower === 'show history' || lower.includes('version history') || lower.includes('show version history')) { showHistory(); return true; }
    if (lower.includes('learning notes') || lower.includes('concepts used') || lower.includes('concepts are in this project')) { learningNotes(); return true; }
    if (lower.includes('accessibility map') || lower.includes('explain accessibility') || lower.includes('accessibility explanation') || lower.includes('accessibility notes')) { accessibilityMap(); return true; }
    if (lower.includes('review project') || lower.includes('review this project') || lower.includes('review this code') || lower.includes('what should i improve')) { reviewProject(); return true; }
    if (lower.includes('describe preview') || lower.includes('describe output') || lower.includes('what will the user see')) { describePreview(); return true; }
    if (lower.includes('project summary') || lower.includes('what did i build') || lower.includes('what project type')) { projectSummary(); return true; }
    if ((lower.includes('explain') || lower.includes('summarize') || lower.includes('summarise') || lower.includes('what does')) && (lower.includes('index.html') || lower.includes('html file') || lower.includes('css') || lower.includes('style.css') || lower.includes('style file') || lower.includes('javascript') || lower.includes('java script') || /\bjs\b/.test(lower) || lower.includes('script.js') || lower.includes('script file'))) { explainProjectFile(command); return true; }
    if (lower.includes('explain simply') || lower.includes('explain this error') || lower.includes('why is this broken')) { explainErrors(false); return true; }
    if (lower.includes('fix and explain')) { explainErrors(true); return true; }
    if (lower.includes('compare before and after') || lower.includes('read before and after') || lower.includes('replay my mistake') || lower.includes('replay change') || lower.includes('replay the change') || lower === 'what changed' || lower.includes('explain this change') || lower.includes('is this risky') || lower.includes('show changed lines') || lower.includes('read only what changed') || lower.includes('compare preview changes') || lower.includes('compare code changes')) { narrateReplay(command); return true; }
    if (lower.startsWith('remember this as') || lower.startsWith('save this command as')) { saveMacro(command); return true; }
    if (lower.startsWith('use macro') || lower.startsWith('run macro')) { runMacro(command); return true; }
    if (lower === 'list macros') { listMacros(); return true; }
    if (lower.startsWith('delete macro')) { deleteMacro(command); return true; }
    if (lower === 'list bookmarks') { listBookmarks(); return true; }
    if (lower.startsWith('read from bookmark') || lower.startsWith('go to bookmark') || lower.startsWith('open bookmark')) { readBookmark(command); return true; }
    if (lower.startsWith('delete bookmark')) { deleteBookmark(command); return true; }
    if (lower.startsWith('bookmark ') && (lower.includes(' as ') || /^bookmark (this|the|current|that)\b/.test(lower))) { saveBookmark(command); return true; }
    if (lower.includes('restore my last work')) { restoreLastWork(false); return true; }
    if (lower.includes('what did i last work on')) { restoreLastWork(true); return true; }
    if (isCodeMapQuestion(lower)) { codeMap(command); return true; }
    if (/\bread\b/.test(lower) && !/\bread\s+paragraph\b/.test(lower) && !lower.includes('page structure')) {
      if (lower.includes('css') || lower.includes('style')) { readCode('css'); return true; }
      if (lower.includes('javascript') || lower.includes('java script') || /\bjs\b/.test(lower) || lower.includes('script')) { readCode('js'); return true; }
      if (lower.includes('html') || lower.includes('markup')) { readCode('html'); return true; }
      if (lower.includes('all') || lower.includes('everything') || lower.includes('whole') || lower.includes('current') || lower.includes('the code') || lower.includes('read code') || lower === 'read') { readCode('all'); return true; }
    }
    if (lower.includes('code map') || lower.includes('codemap') || lower.includes('structure map') || lower.includes('map of the code') || lower.includes('map the code')) { codeMap(command); return true; }
    if ((lower.includes('explain') || lower.includes('what does')) && (lower.includes('javascript') || lower.includes('java script') || /\bjs\b/.test(lower) || lower.includes('the script'))) { explainProjectFile('script.js'); return true; }
    if ((lower.includes('explain') || lower.includes('what does')) && (lower.includes('css') || lower.includes('the style'))) { explainProjectFile('style.css'); return true; }
    if (lower.includes('analyze') || lower.includes('analyse') || lower.includes('find problems') || lower.includes('check the code')) { analyzeCode(); return true; }
    if (lower.includes('summarize') || lower.includes('summarise')) { explainWebsite(true); return true; }
    if (lower.includes('fix the accessibility') || lower.includes('fix accessibility') || lower.includes('fix the accessibility issues')) { applyAllAuditFixes(); return true; }
    if (lower.includes('fix the code') || lower.includes('fix my code') || lower === 'fix' || lower.includes('fix it') || lower.includes('fix the bugs')) { applyAllAuditFixes(); return true; }
    if (lower.includes('futuristic')) { applyDesignPreset('futuristic'); return true; }
    if (lower.includes('add animation') || lower.includes('add animations') || lower.includes('more animation')) { applyDesignPreset('animated'); return true; }
    if (lower.includes('more beautiful') || lower.includes('more colorful') || lower.includes('more colourful') || lower.includes('prettier') || lower.includes('improve the design') || lower.includes('make it pop')) { applyDesignPreset('vibrant'); return true; }
    if (lower.includes('make it more professional') || lower.includes('make it simpler') || lower.includes('make the text easier to read') || lower.includes('make text easier to read') || lower.includes('make the title shorter') || lower.includes('improve navigation') || lower.includes('add footer') || lower.includes('change website name to') || lower.includes('change the website name to') || lower.includes('change the title to') || lower.includes('make the buttons clearer')) { buildWebsite(command, true, { edit: true }); return true; }
    if (/add\s+(an?\s+)?about\s+section/i.test(lower) || /add\s+(an?\s+)?section\s+(about|for)\s+/i.test(lower)) { buildWebsite(command, true, { edit: true }); return true; }
    if (lower.includes('dark mode')) { applyCssEdit('change the background dark'); return true; }
    if (lower.includes('make it accessible') || lower.includes('improve accessibility') || lower.includes('more accessible')) { applyAllAuditFixes(); return true; }
    if (lower.includes('contact') && (lower.includes('section') || lower.includes('form'))) { addContactSection(); return true; }
    if (lower.includes('run preview') || lower.includes('run the preview') || lower.includes('show preview')) { previewHtml(true); return true; }
    if (lower.includes('add javascript') || lower.includes('add interactivity') || lower.includes('more interactive')) { buildWebsite(command, true, { edit: true }); return true; }
    return false;
  }

  function helpText() {
    return t(
      'You can create websites and small apps, improve them, explain files, map the project, check accessibility, preview, and export. You can also use the Python tab for real Python learning: run this code, run with inputs, teach me this code, audio code map, step through this code, next step, what changed, where am I, watch variable total, break when total is greater than 10, or python history. Try: make a quiz app about Python basics.',
      'Aap websites aur chhote apps bana sakte hain, explain kar sakte hain, accessibility check kar sakte hain, preview dekh sakte hain, aur export kar sakte hain. Try kijiye: Python basics ka quiz app banao. Phir boliye: code map, step narration, explain CSS, learning notes, accessibility map, review project, describe preview, ya export website.'
    );
  }

  function isBuildIntent(text) {
    const lower = text.toLowerCase();
    return (
      /\b(build|make|create|generate)\b.*\b(website|site|page|webpage|app|project|quiz|calculator|todo|to-do|flashcard|poll|dashboard|timetable|tracker)\b/i.test(text) ||
      /\b(website|site|page|webpage|app|project|quiz|calculator|todo|to-do|flashcard|poll|dashboard|timetable|tracker)\s+(for|about)\b/i.test(text) ||
      /\b(banao|bana do|banaiye|banaye|banaao)\b/i.test(lower)
    );
  }

  function isReviewIntent(text) {
    const lower = text.toLowerCase();
    return (
      lower.includes('what do you think') ||
      lower.includes('missing') ||
      lower.includes('review') ||
      lower.includes('feedback') ||
      lower.includes('kaisi dikhti') ||
      lower.includes('kya kami') ||
      lower.includes('kya missing')
    );
  }

  function isApplyReviewIntent(text) {
    const lower = text.toLowerCase();
    return (
      lower.includes('add that') ||
      lower.includes('apply that') ||
      lower.includes('do that') ||
      lower.includes('fix missing') ||
      lower.includes('add the missing') ||
      lower.includes('make those changes') ||
      lower.includes('use your suggestions') ||
      lower.includes('jo missing hai add') ||
      lower.includes('woh add karo')
    );
  }

  async function routeIntent(command) {
    try {
      const data = await apiJson('/voice-command', {
        method: 'POST',
        body: JSON.stringify({ text: command }),
      });
      return data;
    } catch (error) {
      return { action: 'chat', confidence: 0.1, slots: {}, text: command };
    }
  }

  function addSectionFromIntent(command, slots = {}) {
    const label = slots.section || command.replace(/^(add|insert|new)\s+section/i, '').trim() || 'New Section';
    snapshotVersion('Before adding section');
    insertAtCursor(`\n<section aria-labelledby="${slugify(label)}-heading">\n  <h2 id="${slugify(label)}-heading">${label}</h2>\n  <p>Add details for ${label.toLowerCase()} here.</p>\n</section>\n`);
    writeOutput(`Added section: ${label}.`, true);
    return true;
  }

  function addContactPage() {
    state.pages[state.currentPage] = getHtml();
    state.pages.contact = state.pages.contact || makeTemplateHtml('club page').replace(/Club Page/g, 'Contact');
    state.currentPage = 'contact';
    setHtml(state.pages.contact);
    snapshotVersion('Added contact page');
    writeOutput('Added and opened the contact page.', true);
    return true;
  }

  async function dispatchIntent(routed, command) {
    if (routed.needs_clarification) {
      writeOutput(routed.message || 'Please clarify what action you want.', true);
      return true;
    }
    const action = routed.action;
    const slots = routed.slots || {};
    if (action === 'chat') return false;
    if (action === 'help_guide') { writeOutput(helpText(), true); return true; }
    if (action === 'walkthrough_page') { await walkthroughPageMap(); return true; }
    if (action === 'walkthrough_keyboard_start') { await walkthroughKeyboardStart(); return true; }
    if (action === 'walkthrough_next_element') { await walkthroughKeyboardMove('next'); return true; }
    if (action === 'walkthrough_prev_element') { await walkthroughKeyboardMove('previous'); return true; }
    if (action === 'walkthrough_pause_issues') { await enableWatchpoint(command, slots); return true; }
    if (action === 'walkthrough_list_watchpoints') { await walkthroughListWatchpoints(); return true; }
    if (action === 'walkthrough_explain_issue') { await walkthroughExplainIssue(); return true; }
    if (action === 'walkthrough_fix_issue') { await walkthroughFixIssue(); return true; }
    if (action === 'walkthrough_compare') { await walkthroughCompare(); return true; }
    if (action === 'walkthrough_stop') { walkthroughStop(); return true; }
    if (action === 'tutorial_start') { await startTutorial(command); return true; }
    if (action === 'tutorial_control') { await handleTutorialCommand(command); return true; }
    if (action === 'breadcrumb') { breadcrumb(); return true; }
    if (action === 'explain_errors') { await explainErrors(command.toLowerCase().includes('fix')); return true; }
    if (action === 'save_macro') return saveMacro(command);
    if (action === 'run_macro') return runMacro(command);
    if (action === 'list_macros') return listMacros();
    if (action === 'delete_macro') return deleteMacro(command);
    if (action === 'save_bookmark') return saveBookmark(command);
    if (action === 'read_bookmark') return readBookmark(command);
    if (action === 'list_bookmarks') return listBookmarks();
    if (action === 'delete_bookmark') return deleteBookmark(command);
    if (action === 'restore_work') return restoreLastWork(command.toLowerCase().includes('what did'));
    if (action === 'set_wake_word') {
      state.wakeWord = command.toLowerCase().replace(/^set wake word to |^change wake word to /, '').trim() || 'hey codeup';
      localStorage.setItem('codeup_wake_word', state.wakeWord);
      state.wakeUntil = Date.now() + 45000;
      writeOutput(`Wake word changed to ${state.wakeWord}.`, true);
      return true;
    }
    if (action === 'pause_voice') { pauseVoice(); return true; }
    if (action === 'resume_voice') { resumeVoice(); return true; }
    if (action === 'stop_speaking') { cancelSpeech(); announce('Speech stopped'); return true; }
    if (action === 'set_voice_language') return false;
    if (action === 'python_run') { await runPythonCode(); return true; }
    if (action === 'python_analyze') { await analyzePythonCode('analyze'); return true; }
    if (action === 'python_teach') { await analyzePythonCode('teach'); return true; }
    if (action === 'python_audio_code_map') { await pythonAudioCodeMap(command); return true; }
    if (action === 'python_step_narration') { await pythonStepNarration(); return true; }
    if (action === 'python_state_watch') { await pythonStateWatch(slots.state_action || 'current', command, slots); return true; }
    if (action === 'python_watch_variable') { await pythonWatchVariable(command, slots); return true; }
    if (action === 'python_conditional_breakpoint') { await pythonConditionalBreakpoint(command, slots); return true; }
    if (action === 'python_explain_errors') { await pythonExplainError(); return true; }
    if (action === 'python_mistake_replay') { await pythonMistakeReplay(); return true; }
    if (action === 'read_code') { readCode(slots.target || 'all'); return true; }
    if (action === 'code_map') { await codeMap(command); return true; }
    if (action === 'step_narration') { await stepNarration(); return true; }
    if (action === 'file_explanation') { await explainProjectFile(slots.target || command); return true; }
    if (action === 'learning_notes') { await learningNotes(); return true; }
    if (action === 'landmarks') { await landmarks(); return true; }
    if (action === 'trainer_notes') { await trainerNotes(); return true; }
    if (action === 'student_recap') { await studentRecap(); return true; }
    if (action === 'screen_reader_prep') { await screenReaderSummary(); return true; }
    if (action === 'run_summary' || action === 'runtime_teacher') { await runWebsite(); return true; }
    if (action === 'debug_website') { await debugWebsite(); return true; }
    if (action === 'debug_fix') { await debugFix(); return true; }
    if (action === 'selector_explainer') { await selectorExplainer(slots.query || command); return true; }
    if (action === 'pilot_report') { await pilotReport(); return true; }
    if (action === 'guided_build_start') { await startGuidedBuild(); return true; }
    if (action === 'screen_reader_tour') { await screenReaderTour(); return true; }
    if (action === 'keyboard_test') { await keyboardTest(); return true; }
    if (action === 'visual_description') { await visualDescription(); return true; }
    if (action === 'readiness_score') { await readinessScore(); return true; }
    if (action === 'teacher_review') { await teacherReview(); return true; }
    if (action === 'version_history') { showHistory(); return true; }
    if (action === 'accessibility_map') { await accessibilityMap(); return true; }
    if (action === 'review_project') { await reviewProject(); return true; }
    if (action === 'describe_preview') { await describePreview(); return true; }
    if (action === 'project_summary') { await projectSummary(); return true; }
    if (action === 'analyze_code') { await analyzeCode(); return true; }
    if (action === 'explain_javascript') { explainJs(); return true; }
    if (action === 'design_preset') { applyDesignPreset(slots.preset || 'vibrant'); return true; }
    if (action === 'add_contact_section') return addContactSection();
    if (action === 'add_js_interactivity') { await buildWebsite(command, true, { edit: true }); return true; }
    if (action === 'navigate_page' || action === 'read_current_section' || action === 'read_next_section') { navigatePreview(command); return true; }
    if (action === 'darken_theme') { applyCssEdit('change the background dark'); return true; }
    if (action === 'lighten_theme') { applyCssEdit('change the background white'); return true; }
    if (action === 'edit_css' && applyCssEdit(command)) return true;
    if (action === 'announce_contrast') { announceContrast(); return true; }
    if (action === 'explain_concept' && explainConcept(command)) return true;
    if (action === 'undo_version') { await undoByVoice(command); return true; }
    if (action === 'review_changes') { await narrateReplay(command); return true; }
    if (action === 'create_multipage_site') { createMultiPageSite(command); return true; }
    if (action === 'add_contact_page') return addContactPage();
    if (action === 'switch_page') { switchPage(slots.page || command); return true; }
    if (action === 'add_section') return addSectionFromIntent(command, slots);
    if (action === 'use_template') { useTemplate(command); return true; }
    if (action === 'save_snippet') { if (handleSnippetCommand(command)) return true; saveSnippet(command.replace(/.*snippet\s*(called|named)?\s*/i, '')); return true; }
    if (action === 'list_snippets') { listSnippets(); return true; }
    if (action === 'load_snippet') { if (handleSnippetCommand(command)) return true; loadSnippet(command.replace(/.*snippet\s*(called|named)?\s*/i, '')); return true; }
    if (action === 'delete_snippet') { if (handleSnippetCommand(command)) return true; deleteSnippet(slots.snippet_name || ''); return true; }
    if (action === 'apply_audit_fixes') { await applyAllAuditFixes(); return true; }
    if (action === 'apply_review') { await applyReviewSuggestion(command, true); return true; }
    if (action === 'review_site') { await reviewWebsite(true); return true; }
    if (action === 'preview_site') { await previewHtml(true); return true; }
    if (action === 'audit_site') { await auditWebsite(true); return true; }
    if (action === 'outline_site') { outlineWebsite(true); return true; }
    if (action === 'export_site') { await exportHtml(); return true; }
    if (action === 'reset_session') { await resetSession(); return true; }
    if (action === 'clear_editor') { await resetSession(); return true; }
    if (action === 'explain_site') { await explainWebsite(true); return true; }
    if (action === 'sonify_site') { sonifyHtml(); return true; }
    if (action === 'polish_html') { await polishHtml(); return true; }
    if (action === 'edit_website') { await buildWebsite(command, true, { edit: true }); return true; }
    if (action === 'build_site') { await buildWebsite(slots.prompt || command, true); return true; }
    return false;
  }

  async function routeNaturalCommand(transcript) {
    try {
      const data = await apiJson('/voice-action', {
        method: 'POST',
        body: JSON.stringify({
          transcript,
          html: getHtml(),
          language: lang(),
        }),
      });
      return data;
    } catch (error) {
      return null;
    }
  }

  async function executeStructuredAction(action) {
    if (!action || !action.action || action.action === 'unknown') return false;
    const act = action.action;
    const confirmation = action.spoken_confirmation || '';

    if (act === 'generate_page' || act === 'edit_page') {
      if (action.html) {
        snapshotVersion('Before AI action');
        if (act === 'generate_page') { state.currentPage = 'home'; state.pages = {}; }
        setHtml(action.html);
        snapshotVersion(confirmation || 'AI edit');
        try { await publish(action.html); } catch (e) {}
        writeOutput(confirmation || t('Page updated.', 'Page update ho gaya.'), true);
        return true;
      }
    }
    if (act === 'append_html' || act === 'add_component') {
      if (action.html) {
        snapshotVersion('Before adding component');
        insertAtCursor('\n' + action.html + '\n');
        writeOutput(confirmation || t('Content added.', 'Content add ho gaya.'), true);
        return true;
      }
    }
    if (act === 'replace_html_element' || act === 'update_text' || act === 'update_attribute' || act === 'add_alt_text' || act === 'fix_accessibility_issue') {
      if (action.html) {
        snapshotVersion('Before AI edit');
        setHtml(action.html);
        snapshotVersion(confirmation || 'Edited page');
        try { await publish(action.html); } catch (e) {}
        writeOutput(confirmation || t('Edit applied.', 'Edit apply ho gaya.'), true);
        return true;
      }
    }
    if (act === 'remove_element') {
      if (action.html) {
        snapshotVersion('Before removal');
        setHtml(action.html);
        snapshotVersion(confirmation || 'Removed element');
        writeOutput(confirmation || t('Element removed.', 'Element hata diya.'), true);
        return true;
      }
    }
    if (act === 'preview_page') { await previewHtml(true); return true; }
    if (act === 'explain_structure') { await walkthroughPageMap(); return true; }
    if (act === 'audit_accessibility') { await auditWebsite(true); return true; }
    if (act === 'sonify_structure') { sonifyHtml(); return true; }
    if (act === 'save_snippet') { saveSnippet(action.snippet_name || ''); return true; }
    if (act === 'list_snippets') { listSnippets(); return true; }
    if (act === 'load_snippet') { loadSnippet(action.snippet_name || ''); return true; }
    if (act === 'undo') { await undoByVoice('undo'); return true; }
    if (act === 'clear_editor') { await resetSession(); return true; }
    if (confirmation) { writeOutput(confirmation, true); return true; }
    return false;
  }

  function isSnippetCommand(lower) {
    return /\b(save|load|show|list|delete)\b.*\bsnippet/i.test(lower) ||
      /\bsnippet\b.*\b(save|load|show|list|delete)\b/i.test(lower) ||
      /\b(mere|mera)\s+snippets?\b/i.test(lower) ||
      /\bsnippet\b.*\b(dikhao|batao)\b/i.test(lower);
  }

  function handleSnippetCommand(command) {
    const lower = command.toLowerCase();
    if (/\b(show|list)\b.*\bsnippets?\b/i.test(lower) || /\b(mere|mera)\s+snippets?\b/i.test(lower) || /\bsnippets?\s+(dikhao|batao)\b/i.test(lower)) {
      listSnippets();
      return true;
    }
    const saveMatch = command.match(/save\s+(?:this\s+(?:page|website|site)\s+)?(?:as\s+)?(?:a\s+)?snippet\s+(?:called\s+|named\s+)?(.+)/i)
      || command.match(/snippet\s+(?:save\s+(?:karo|kar\s+do)\s+)?(.+?\s+naam\s+se)/i)
      || command.match(/(.+?)\s+naam\s+(?:se|ka)\s+snippet\s+save\s+karo/i);
    if (saveMatch) {
      const name = saveMatch[1].replace(/^\s*(as\s+|called\s+|named\s+)+/i, '').replace(/\b(naam\s+se|called|named)\b/gi, '').trim();
      saveSnippet(name);
      return true;
    }
    const loadMatch = command.match(/load\s+(?:the\s+)?snippet\s+(?:called\s+|named\s+)?(.+)/i)
      || command.match(/(.+?)\s+(?:wala|naam\s+ka)\s+snippet\s+load\s+karo/i);
    if (loadMatch) {
      const name = loadMatch[1].replace(/\b(called|named|wala|naam\s+ka)\b/gi, '').trim();
      loadSnippet(name);
      return true;
    }
    const deleteMatch = command.match(/(?:delete|remove)\s+(?:the\s+)?snippet\s+(?:called\s+|named\s+)?(.+)/i)
      || command.match(/(.+?)\s+(?:wala|naam\s+ka)\s+snippet\s+(?:delete|hatao)/i);
    if (deleteMatch) {
      const name = deleteMatch[1].replace(/\b(called|named|wala|naam\s+ka)\b/gi, '').trim();
      deleteSnippet(name);
      refreshSnippetSelect();
      return true;
    }
    return false;
  }

  async function handleVoiceCommand(raw) {
    const command = repairCommand(raw.trim());
    if (!command) return;
    recordCommand(command);
    nextAsyncToken();
    cancelSpeech();
    const lower = command.toLowerCase();
    if (lower.includes('stop everything') || lower.includes('stop speaking') || lower === 'stop'
        || lower === 'cancel' || lower.includes('be quiet') || lower.includes('chup') || lower.includes('sab rok')) {
      stopEverything();
      return;
    }
    if (lower.includes('clear command')) {
      const field = $('commandInput');
      if (field) field.value = '';
      writeOutput(t('Command box cleared.', 'Command box clear ho gaya.'), true);
      return;
    }
    if (lower.startsWith('set wake word to ') || lower.startsWith('change wake word to ')) {
      state.wakeWord = lower.replace(/^set wake word to |^change wake word to /, '').trim() || 'hey codeup';
      localStorage.setItem('codeup_wake_word', state.wakeWord);
      state.wakeUntil = Date.now() + 45000;
      writeOutput(`Wake word changed to ${state.wakeWord}.`, true);
      return;
    }
    const wakeIndex = lower.indexOf(state.wakeWord);
    if (wakeIndex !== -1) {
      state.wakeUntil = Date.now() + 45000;
      const afterWake = command.slice(wakeIndex + state.wakeWord.length).trim();
      if (!state.activeVoice) startVoice({ silent: true });
      if (!afterWake) {
        writeOutput(`Heard ${state.wakeWord}. Say a CodeUp command.`, true);
        return;
      }
      await handleVoiceCommand(afterWake);
      return;
    }
    state.wakeUntil = Date.now() + 45000;
    writeOutput(`${t('Heard', 'Suna')}: ${command}`);
    if (handleIdeCommand(command, lower)) return;

    if (lower.includes('voice off') || lower.includes('stop voice') || lower.includes('voice band karo') || lower.includes('sunna band karo')) {
      stopVoice();
      return;
    }
    if (lower.includes('pause voice') || lower.includes('stop listening') || lower.includes('awaaz rok') || lower.includes('ruk jao')) {
      pauseVoice();
      return;
    }
    if (lower.includes('voice on karo') || lower.includes('dobara sunna shuru karo')) {
      resumeVoice();
      return;
    }
    if (state.paused) {
      if (lower.includes('resume') || lower.includes('start listening') || lower.includes('voice on') || lower.includes('phir se') || lower.includes('chalu')) {
        resumeVoice();
      }
      return;
    }
    if (lower.includes('stop speaking') || lower.includes('quiet') || lower.includes('chup')) {
      cancelSpeech();
      announce('Speech stopped');
      return;
    }
    if (lower.includes('voice language') || lower.includes('speech language') || lower.includes('bhasha')) {
      const VME = window.VoiceMemoryEngine;
      if (VME) {
        let mode = 'auto';
        if (lower.includes('hindi') || lower.includes('à¤¹à¤¿à¤‚à¤¦à¥€')) mode = 'hi';
        else if (lower.includes('english') || lower.includes('à¤…à¤‚à¤—à¥à¤°à¥‡à¤œà¤¼à¥€')) mode = 'en';
        VME.setVoiceLangMode(mode);
        localStorage.setItem('codeup_voice_lang_mode', mode);
        const labels = { auto: 'Auto-detect', en: 'English', hi: 'Hindi' };
        writeOutput(t(`Voice language set to ${labels[mode]}.`, `Voice bhasha ${labels[mode]} set ho gayi.`), true);
        if (state.activeVoice && !state.paused) {
          stopActiveRecognition();
          setTimeout(startActiveRecognition, 200);
        }
      }
      return;
    }
    if (lower.includes('help') || lower.includes('madad')) {
      await chatWithAI(command, true);
      return;
    }
    if (handleIdeCommand(command, lower)) return;
    const routed = await routeIntent(command);
    if (await dispatchIntent(routed, command)) return;
    if (lower.includes('next heading') || lower.includes('previous heading') || lower.includes('next section') || lower.includes('previous section') || /read paragraph\s+\d+/i.test(command)) {
      navigatePreview(command);
      return;
    }
    if (lower.includes('high contrast') && applyCssEdit(command)) return;
    if (lower.includes('contrast')) {
      announceContrast();
      return;
    }
    if ((lower.includes('what is') || lower.includes('what does') || lower.includes('explain concept')) && explainConcept(command)) return;
    if (lower.includes('go back') || lower.startsWith('undo')) {
      await undoByVoice(command);
      return;
    }
    if (lower.includes('what changed') || lower.includes('read before and after') || lower.includes('explain this change') || lower.includes('is this risky') || lower.includes('compare versions') || lower.includes('review changes')) {
      snapshotVersion('Current version for comparison');
      await reviewChanges();
      return;
    }
    if (lower.includes('multi page') || lower.includes('multiple page') || lower.includes('homepage plus')) {
      createMultiPageSite(command);
      return;
    }
    if (lower.includes('go to page') || lower.includes('open page') || lower.includes('switch to page')) {
      switchPage(command);
      return;
    }
    if (lower.includes('template')) {
      useTemplate(command);
      return;
    }
    if (applyCssEdit(command)) return;
    if (isApplyReviewIntent(command)) {
      await applyReviewSuggestion(command, true);
      return;
    }
    if (isReviewIntent(command)) {
      await reviewWebsite(true);
      return;
    }
    if (lower.includes('preview') || lower.includes('show website') || lower.includes('run website') || lower.includes('dikhao')) {
      await previewHtml(true);
      return;
    }
    if (lower.includes('audit') || lower.includes('accessibility score') || lower.includes('check accessibility')) {
      await auditWebsite(true);
      return;
    }
    if (lower.includes('outline') || lower.includes('page structure') || lower.includes('sections')) {
      outlineWebsite(true);
      return;
    }
    if (lower.includes('export') || lower.includes('download')) {
      await exportHtml();
      return;
    }
    if (lower.includes('reset session') || lower === 'reset') {
      await resetSession();
      return;
    }
    if (lower.includes('explain') || lower.includes('describe') || lower.includes('looks') || lower.includes('samjhao') || lower.includes('kaisi dikhti')) {
      await explainWebsite(true);
      return;
    }
    if (lower.includes('sonify') || lower.includes('sound') || lower.includes('audio structure') || lower.includes('sunao')) {
      sonifyHtml();
      return;
    }
    if (lower.includes('polish') || lower.includes('fix html') || lower.includes('improve') || lower.includes('theek')) {
      await polishHtml();
      return;
    }
    if (addHtmlFromSpeech(command)) return;
    if (/\b(editor|page)\s+(clear|saaf)\s+karo\b/i.test(lower) || /\bnaya\s+page\s+shuru\s+karo\b/i.test(lower)) {
      await resetSession();
      return;
    }
    if (/\bpage\s+preview\s+karo\b/i.test(lower) || /\bwebsite\s+dikhao\b/i.test(lower)) {
      await previewHtml(true);
      return;
    }
    if (/\bpage\s+ka\s+structure\s+samjhao\b/i.test(lower) || /\bwebsite\s+ka\s+layout\s+batao\b/i.test(lower)) {
      await walkthroughPageMap();
      return;
    }
    if (/\bpage\s+structure\s+sonify\s+karo\b/i.test(lower) || /\blayout\s+ka\s+audio\s+structure\s+sunao\b/i.test(lower)) {
      sonifyHtml();
      return;
    }
    if (/\baccessibility\s+issues?\s+check\s+karo\b/i.test(lower) || /\bmissing\s+alt\s+text\s+fix\s+karo\b/i.test(lower) || /\baccessibility\s+fix\s+karo\b/i.test(lower)) {
      await auditWebsite(true);
      return;
    }
    if (isSnippetCommand(lower)) {
      if (handleSnippetCommand(command)) return;
    }

    const buildMatch = command.match(
      /(?:build|make|create|generate|banao|bana do|website for|app for|app about|project for|project about|quiz about|calculator for|ke liye website)\s+(.+)/i
    );
    if (buildMatch || isBuildIntent(command)) {
      await buildWebsite(buildMatch ? buildMatch[1] : command, true);
      return;
    }
    if (command.length > 10) {
      writeOutput(t('Processing...', 'Process ho raha hai...'));
      const action = await routeNaturalCommand(command);
      if (action && action.success && await executeStructuredAction(action)) return;
    }

    await chatWithAI(command, true);
  }

  async function handleStudentTextCore(raw) {
    const text = repairCommand(raw.trim());
    if (!text) {
      writeOutput(t(
        'Type or say what you want to build, or ask a question about your website.',
        'Aap kya banana chahte hain likhiye ya apni website ke baare mein poochiye.'
      ), true);
      return;
    }
    recordCommand(text);
    nextAsyncToken();
    state.wakeUntil = Date.now() + 45000;
    const lower = text.toLowerCase();
    if (lower.includes('stop everything') || lower.includes('stop speaking') || lower === 'stop'
        || lower === 'cancel' || lower.includes('clear command') || lower.includes('be quiet')) {
      await handleVoiceCommand(text);
      return;
    }
    if (handleIdeCommand(text, lower)) return;
    const routed = await routeIntent(text);
    if (routed.action !== 'chat' || routed.needs_clarification) {
      await handleVoiceCommand(text);
      return;
    }
    const isBuildRequest = isBuildIntent(text);
    if (isBuildRequest) {
      await handleVoiceCommand(text);
      return;
    }
    if (isApplyReviewIntent(text) || isReviewIntent(text)) {
      await handleVoiceCommand(text);
      return;
    }
    if (
      lower.includes('preview') ||
      lower.includes('explain') ||
      lower.includes('describe') ||
      lower.includes('sonify') ||
      lower.includes('audit') ||
      lower.includes('outline') ||
      lower.includes('export') ||
      lower.includes('download') ||
      lower.includes('reset session') ||
      lower.includes('polish') ||
      lower.includes('pause voice') ||
      lower.includes('resume voice') ||
      lower.includes('stop speaking') ||
      lower.includes('add heading') ||
      lower.includes('add paragraph') ||
      lower.includes('add button') ||
      lower.includes('next heading') ||
      lower.includes('previous section') ||
      lower.includes('read paragraph') ||
      lower.includes('contrast') ||
      lower.includes('template') ||
      lower.includes('multi page') ||
      lower.includes('go back') ||
      lower.includes('what changed') ||
      lower.includes('read before and after') ||
      lower.includes('explain this change') ||
      lower.includes('is this risky') ||
      lower.includes('voice language') ||
      lower.includes('speech language') ||
      lower.includes('bhasha') ||
      lower.includes('walk me through') ||
      lower.includes('audio accessibility walkthrough') ||
      lower.includes('read the page structure') ||
      lower.includes('start keyboard journey') ||
      lower.includes('next interactive element') ||
      lower.includes('previous interactive element') ||
      lower.includes('pause on accessibility issues') ||
      lower.includes('list accessibility watchpoints') ||
      lower.includes('explain first issue') ||
      lower.includes('why is this inaccessible') ||
      lower.includes('fix this issue') ||
      lower.includes('compare accessibility before and after') ||
      lower.includes('stop walkthrough') ||
      lower.includes('wake word') ||
      lower.includes('make the heading') ||
      lower.includes('make heading') ||
      lower.includes('change the background') ||
      lower.includes('background') ||
      lower.includes('font') ||
      lower.includes('text color') ||
      lower.includes('more spacing') ||
      lower.includes('less spacing') ||
      lower.includes('high contrast') ||
      lower.includes('rounded') ||
      lower.includes('center') ||
      lower.includes('voice off') ||
      lower.includes('voice band karo') ||
      lower.includes('voice on karo') ||
      lower.includes('sunna band karo') ||
      lower.includes('dobara sunna') ||
      /snippet/i.test(lower) ||
      /\b(clear|saaf)\s+karo\b/i.test(lower) ||
      /\bnaya\s+page\b/i.test(lower) ||
      /\bpage\s+preview\s+karo\b/i.test(lower) ||
      /\bwebsite\s+dikhao\b/i.test(lower) ||
      /\bstructure\s+samjhao\b/i.test(lower) ||
      /\blayout\s+batao\b/i.test(lower) ||
      /\bsonify\s+karo\b/i.test(lower) ||
      /\baudio\s+structure\s+sunao\b/i.test(lower) ||
      /\baccessibility\s+issues?\s+check\s+karo\b/i.test(lower) ||
      /\balt\s+text\s+fix\s+karo\b/i.test(lower) ||
      /\bheading\s+ko\b.*\bkar\s+do\b/i.test(lower) ||
      /\bimage\s+add\s+karo\b/i.test(lower)
    ) {
      await handleVoiceCommand(text);
      return;
    }
    if (text.length > 10) {
      writeOutput(t('Processing...', 'Process ho raha hai...'));
      const action = await routeNaturalCommand(text);
      if (action && action.success && await executeStructuredAction(action)) return;
    }

    await chatWithAI(text, true);
  }

  function transcriptFromEvent(event) {
    const result = event.results[event.results.length - 1];
    return result && result[0] ? result[0].transcript : '';
  }

  function isResumeVoiceCommand(lower) {
    return lower.includes('resume voice') ||
      lower.includes('start listening') ||
      lower.includes('voice on') ||
      lower.includes('phir se') ||
      lower.includes('chalu');
  }

  function stopActiveRecognition() {
    const recognition = state.activeRecognition;
    state.activeRecognition = null;
    if (!recognition) return;
    try { recognition.stop(); } catch (error) {}
  }

  function stopWakeListener() {
    const recognition = state.wakeRecognition;
    state.wakeRecognition = null;
    state.wakeListening = false;
    if (!recognition) return;
    try { recognition.stop(); } catch (error) {}
  }

  function startActiveRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      speak(t('Voice recognition is not supported in this browser. Please use Chrome or Edge.', 'Is browser mein voice recognition support nahi hai. Chrome ya Edge use karein.'));
      return;
    }
    if (!state.activeVoice || state.paused || state.manualVoiceStop) return;
    if (state.activeRecognition) {
      try { state.activeRecognition.stop(); } catch (e) {}
      state.activeRecognition = null;
    }
    const recognition = new SpeechRecognition();
    state.activeRecognition = recognition;
    recognition.continuous = true;
    recognition.interimResults = true;
    const vmeMode = window.VoiceMemoryEngine ? window.VoiceMemoryEngine.getVoiceLangMode() : null;
    if (vmeMode === 'hi') recognition.lang = 'hi-IN';
    else if (vmeMode === 'en') recognition.lang = 'en-US';
    else recognition.lang = isHindi() ? 'hi-IN' : 'en-US';
    recognition.onstart = () => {
      updateVoiceButton();
      announce(t('Voice command listening.', 'Voice command sun raha hai.'));
    };
    recognition.onresult = (event) => {
      const result = event.results[event.results.length - 1];
      if (!result) return;
      if (!result.isFinal) {
        if (window.VoiceMemoryEngine) {
          const vmeState = window.VoiceMemoryEngine.getState();
          if (vmeState === 'SPEAKING' || vmeState === 'RESPONDING') {
            window.VoiceMemoryEngine.interrupt();
          }
        }
        return;
      }
      const transcript = result[0] ? result[0].transcript : '';
      cancelSpeech();
      handleVoiceCommandWithInterrupt(transcript);
    };
    recognition.onerror = () => updateVoiceButton();
    recognition.onend = () => {
      if (state.activeRecognition !== recognition) return;
      state.activeRecognition = null;
      updateVoiceButton();
      if (state.activeVoice && !state.paused && !state.manualVoiceStop) {
        setTimeout(startActiveRecognition, 150);
      }
    };
    try {
      recognition.start();
    } catch (error) {
      if (state.activeRecognition === recognition) state.activeRecognition = null;
      state.activeVoice = false;
      state.paused = false;
      if (window.VoiceMemoryEngine) window.VoiceMemoryEngine.setVoiceActive(false);
      updateVoiceButton();
      speak(t('Could not start voice.', 'Voice start nahi ho payi.'));
      startWakeListener();
    }
  }

  function startVoice(options = {}) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      speak(t('Voice recognition is not supported in this browser. Please use Chrome or Edge.', 'Is browser mein voice recognition support nahi hai. Chrome ya Edge use karein.'));
      return;
    }
    if (state.activeVoice && !state.paused) {
      if (!options.silent) speak(t('Voice is already on.', 'Voice pehle se on hai.'));
      return;
    }
    cancelSpeech();
    stopWakeListener();
    state.activeVoice = true;
    state.paused = false;
    state.manualVoiceStop = false;
    state.wakeUntil = Date.now() + 45000;
    if (window.VoiceMemoryEngine) window.VoiceMemoryEngine.setVoiceActive(true);
    updateVoiceButton();
    startActiveRecognition();
    if (!options.silent) {
      speak(t('Voice on. You can code hands free.', 'Voice on hai. Aap bina keyboard ke code kar sakte hain.'));
    }
  }

  async function handleStudentText(raw) {
    const text = (raw || '').trim();
    if (!text) {
      await handleStudentTextCore(raw);
      return;
    }
    const lower = text.toLowerCase();
    if (shouldUsePythonStateWatch(lower)) {
      await handleStudentTextCore(text);
      return;
    }
    if (isTutorialControlCommand(lower)) {
      await handleTutorialCommand(text);
      return;
    }
    await handleStudentTextCore(text);
    if (isMacroWorthyCommand(text)) {
      state.lastCommand = text;
    }
    if (shouldValidateTutorialCommand(lower)) await validateTutorialProgress(text);
    if (state.track && state.track.active && state.track.guided && !isTutorialControlCommand(lower)) await validateGuidedProgress();
  }

  function startWakeListener() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition || state.wakeListening || (state.activeVoice && !state.paused && !state.manualVoiceStop)) return;
    const recognition = new SpeechRecognition();
    state.wakeRecognition = recognition;
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = isHindi() ? 'hi-IN' : 'en-US';
    recognition.onstart = () => {
      state.wakeListening = true;
      updateVoiceButton();
      announce(`Wake word listener ready. Say ${state.wakeWord}.`);
    };
    recognition.onresult = (event) => {
      const transcript = transcriptFromEvent(event);
      const lower = transcript.toLowerCase();
      if (isResumeVoiceCommand(lower) && state.paused) {
        resumeVoice();
        return;
      }
      const wakeIndex = lower.indexOf(state.wakeWord);
      if (wakeIndex === -1) {
        announce(`Waiting for ${state.wakeWord}`);
        return;
      }
      const afterWake = transcript.slice(wakeIndex + state.wakeWord.length).trim();
      startVoice({ silent: true });
      if (afterWake) handleVoiceCommand(afterWake);
      else writeOutput(`Heard ${state.wakeWord}. Say a CodeUp command.`, true);
    };
    recognition.onerror = () => updateVoiceButton();
    recognition.onend = () => {
      if (state.wakeRecognition !== recognition) return;
      state.wakeRecognition = null;
      state.wakeListening = false;
      updateVoiceButton();
      if (!state.activeVoice || state.paused) {
        setTimeout(() => {
          startWakeListener();
        }, 700);
      }
    };
    try { recognition.start(); } catch (error) { state.wakeRecognition = null; state.wakeListening = false; }
  }

  function stopVoice() {
    const wasActive = state.activeVoice || state.paused;
    state.activeVoice = false;
    state.paused = false;
    state.manualVoiceStop = true;
    if (window.VoiceMemoryEngine) window.VoiceMemoryEngine.setVoiceActive(false);
    stopActiveRecognition();
    updateVoiceButton();
    startWakeListener();
    if (wasActive) speak(t('Voice off. Say the wake word or press the Voice button to start again.', 'Voice off hai. Dobara shuru karne ke liye wake word bolein ya Voice button dabayein.'));
  }

  function pauseVoice() {
    if (!state.activeVoice && !state.paused) {
      writeOutput(t('Voice is already off.', 'Voice pehle se off hai.'), true);
      return;
    }
    state.paused = true;
    state.manualVoiceStop = true;
    stopActiveRecognition();
    updateVoiceButton();
    startWakeListener();
    speak(t('Voice paused. Say resume voice when you want commands again.', 'Voice pause hai. Dobara command ke liye resume voice boliye.'));
  }

  function resumeVoice() {
    if (!state.paused) {
      startVoice();
      return;
    }
    stopWakeListener();
    state.activeVoice = true;
    state.paused = false;
    state.manualVoiceStop = false;
    updateVoiceButton();
    startActiveRecognition();
    speak(t('Voice resumed.', 'Voice resume ho gayi.'));
  }

  function toggleVoice() {
    if (state.activeVoice) stopVoice();
    else startVoice();
  }

  function updateVoiceButton() {
    const button = $('voiceButton');
    if (!button) return;
    const activelyListening = state.activeVoice && !state.paused;
    button.classList.toggle('cu-button-voice--active', activelyListening);
    button.classList.toggle('cu-button-voice--paused', state.paused);
    button.setAttribute('aria-pressed', activelyListening ? 'true' : 'false');
    button.textContent = state.paused
      ? 'Voice Paused'
      : activelyListening
        ? 'Voice On'
        : 'Voice Off';
    const statusEl = $('voiceStatus');
    const railStatus = $('voiceRailStatus');
    if (railStatus) railStatus.textContent = state.paused ? 'paused' : state.activeVoice ? 'on' : 'off';
    if (statusEl) {
      statusEl.textContent = state.paused ? 'Voice paused' : activelyListening ? 'Voice on â€” listening' : 'Voice off';
      statusEl.setAttribute('data-voice', state.paused ? 'paused' : activelyListening ? 'on' : 'off');
    }
  }

  async function submitCommandFromInput() {
    const field = $('commandInput');
    const value = field ? field.value.trim() : '';
    if (field) field.value = '';
    await handleStudentText(value);
  }
  function isPaletteOpen() {
    const overlay = $('paletteOverlay');
    return !!(overlay && !overlay.hidden);
  }

  function paletteFocusables() {
    const dialog = $('commandPalette');
    if (!dialog) return [];
    return [...dialog.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
      .filter((el) => !el.disabled);
  }

  function openCommandPalette() {
    const overlay = $('paletteOverlay');
    const dialog = $('commandPalette');
    const opener = $('openPaletteBtn');
    if (!overlay) return;
    state.paletteOpener = (document.activeElement && document.activeElement.focus) ? document.activeElement : opener;
    overlay.hidden = false;
    document.body.classList.add('ide-palette-open');
    if (opener) opener.setAttribute('aria-expanded', 'true');
    if (dialog && dialog.focus) dialog.focus();
  }

  function closeCommandPalette(opts) {
    opts = opts || {};
    const overlay = $('paletteOverlay');
    const opener = $('openPaletteBtn');
    if (!overlay || overlay.hidden) return;
    overlay.hidden = true;
    document.body.classList.remove('ide-palette-open');
    if (opener) opener.setAttribute('aria-expanded', 'false');
    if (opts.returnFocus !== false && state.paletteOpener && state.paletteOpener.focus) state.paletteOpener.focus();
  }

  function paletteTrapFocus(event) {
    if (!isPaletteOpen() || event.key !== 'Tab') return;
    const items = paletteFocusables();
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }

  function setupUi() {
    document.title = 'CodeUp';
    const pageTitle = document.querySelector('.cu-title');
    if (pageTitle) pageTitle.textContent = 'CodeUp';
    replaceButton('generateBtn', 'Generate', 'Generate a website from the command box', generateFromCommand);
    replaceButton('runBtn', 'Run', 'Run live preview of HTML, CSS, and JavaScript', () => previewHtml(true));
    replaceButton('clearOutputBtn', 'Clear', 'Clear the output panel', clearOutput);
    replaceButton('readOutputBtn', 'Read Output', 'Read the current output aloud', readOutput);
    replaceButton('toolbarTutorialBtn', 'Tutorial', 'Start the guided tutorial', () => startTutorial(''));
    replaceButton('runPythonBtn', 'Run Python', 'Run the Python program in the Python editor', runPythonCode);
    replaceButton('teachPythonBtn', 'Teach Python', 'Teach the Python code in the Python editor', () => analyzePythonCode('teach'));
    replaceButton('pythonMapBtn', 'Python Map', 'Hear an audio map of the Python code', pythonAudioCodeMap);
    replaceButton('pythonWatchBtn', 'Variable Watch', 'Read Python variable state', pythonWatchVariable);
    replaceButton('pythonExampleVariablesBtn', 'Variables', 'Load Python variables and print example', () => loadPythonExample('variables'));
    replaceButton('pythonExampleLoopBtn', 'Loop', 'Load Python loop with total example', () => loadPythonExample('loop'));
    replaceButton('pythonExampleInputBtn', 'Input', 'Load Python input greeting example', () => loadPythonExample('input'));
    replaceButton('pythonExampleFunctionBtn', 'Function', 'Load Python function add example', () => loadPythonExample('function'));
    replaceButton('pythonExampleConditionBtn', 'Condition', 'Load Python condition example', () => loadPythonExample('condition'));
    replaceButton('pythonAddInputBtn', 'Add Input', 'Add this value to the Python input queue', addPythonInputFromUi);
    replaceButton('pythonRunWithInputsBtn', 'Run with Inputs', 'Run Python using the queued input values', runPythonWithInputs);
    replaceButton('pythonClearInputsBtn', 'Clear Inputs', 'Clear queued Python input values', () => clearPythonInputs(true));
    replaceButton('pythonBreakpointBtn', 'Check Breakpoint', 'Check a conditional audio breakpoint against the Python code', () => pythonConditionalBreakpoint());
    replaceButton('pythonPrevStepBtn', 'Previous Step', 'Move to the previous Python execution step', () => pythonStateWatch('previous'));
    replaceButton('pythonNextStepBtn', 'Next Step', 'Move to the next Python execution step', () => pythonStateWatch('next'));
    replaceButton('pythonExplainStepBtn', 'Explain Step', 'Explain the current Python execution step', () => pythonStateWatch('current'));
    replaceButton('pythonWhatChangedBtn', 'What Changed?', 'Explain what changed in the current Python step', () => pythonStateWatch('what_changed'));
    replaceButton('pythonWhereAmIBtn', 'Where Am I?', 'Explain where I am in the Python program', () => pythonStateWatch('where'));
    replaceButton('pythonRepeatStepBtn', 'Repeat Step', 'Repeat the current Python step', () => pythonStateWatch('repeat'));
    replaceButton('pythonExplainConditionBtn', 'Explain Condition', 'Explain the nearest Python condition result', () => pythonStateWatch('condition'));
    replaceButton('pythonStepIntoBtn', 'Step Into', 'Step into the next Python function call', () => pythonStateWatch('step_into'));
    replaceButton('pythonStepOutBtn', 'Step Out', 'Step out to the current Python function return', () => pythonStateWatch('step_out'));
    replaceButton('pythonExplainFunctionBtn', 'Explain Function', 'Explain the current Python function call', () => pythonStateWatch('function'));
    replaceButton('pythonFunctionArgsBtn', 'What Arguments?', 'Explain Python function arguments', () => pythonStateWatch('arguments'));
    replaceButton('pythonFunctionReturnBtn', 'What Returned?', 'Explain what the Python function returned', () => pythonStateWatch('return'));
    replaceButton('pythonFunctionBackBtn', 'Go Back Where?', 'Explain where Python goes after the function returns', () => pythonStateWatch('go_back'));
    replaceButton('pythonHistoryBtn', 'Review History', 'Review Python learning history', showPythonHistory);
    replaceButton('pythonClearHistoryBtn', 'Clear History', 'Clear Python learning history', clearPythonHistory);
    replaceButton('analyzeBtn', 'Analyze', 'Analyze the code for issues', analyzeCode);
    replaceButton('fixBtn', 'Fix', 'Fix accessibility and code issues', applyAllAuditFixes);
    replaceButton('readBtn', 'Read Code', 'Read the current editor aloud', () => readCode(state.activeTab || 'html'));
    replaceButton('codeMapBtn', 'Code Map', 'Hear a beginner-friendly map of the code', codeMap);
    replaceButton('auditBtn', 'Audit', 'Audit accessibility and page quality', () => auditWebsite(true));
    replaceButton('runWebsiteBtn', 'Run Website', 'Explain what happens when this website runs', runWebsite);
    replaceButton('debugBtn', 'Debug', 'Debug broken HTML, CSS, and JavaScript connections like a teacher', () => debugWebsite());
    replaceButton('readinessBtn', 'Readiness', 'Check if this website is ready to share', readinessScore);
    replaceButton('outlineBtn', 'Outline', 'Summarize the website outline', () => outlineWebsite(true));
    replaceButton('saveSnippetBtn', 'Save Snippet', 'Save HTML, CSS, and JavaScript as a named snippet', saveSnippetFromUi);
    replaceButton('loadSnippetBtn', 'Load Snippet', 'Load a saved snippet', loadSnippetFromUi);
    replaceButton('deleteSnippetBtn', 'Delete Snippet', 'Delete the selected snippet', deleteSnippetFromUi);
    replaceButton('exportBtn', 'Export', 'Export website as HTML or project ZIP', exportHtml);
    replaceButton('walkthroughBtn', 'Walkthrough', 'Audio accessibility walkthrough of current website', walkthroughPageMap);
    replaceButton('resetBtn', 'Reset', 'Reset this session', resetSession);
    replaceButton('voiceButton', 'Voice Off', 'Toggle voice control', toggleVoice);
    replaceButton('helpBtn', 'Help', 'Hear what CodeUp can do', () => writeOutput(helpText(), true));
    replaceButton('sendCommandBtn', 'Run Command', 'Run the typed command', submitCommandFromInput);
    replaceButton('stopBtn', 'Stop', 'Stop speaking immediately', stopEverything);
    replaceButton('tutorialStartBtn', 'Start Tutorial', 'Start the guided web tutorial', () => startTutorial(''));
    replaceButton('tutorialContinueBtn', 'Continue', 'Continue the guided tutorial', continueTutorial);
    replaceButton('tutorialHintBtn', 'Hint', 'Hear a tutorial hint', tutorialHint);
    replaceButton('tutorialExitBtn', 'Exit', 'Exit the guided tutorial', exitTutorial);

    const field = $('commandInput');
    if (field) {
      const clone = field.cloneNode(true);
      field.replaceWith(clone);
      clone.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        cancelSpeech();
        submitCommandFromInput();
      });
    }
    const pythonInputValue = $('pythonInputValue');
    if (pythonInputValue) {
      pythonInputValue.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        addPythonInputFromUi();
      });
    }
    const pythonBreakpointInput = $('pythonBreakpointInput');
    if (pythonBreakpointInput) {
      pythonBreakpointInput.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        pythonConditionalBreakpoint();
      });
    }
    document.addEventListener('click', (event) => {
      const chip = event.target && event.target.closest ? event.target.closest('[data-cmd]') : null;
      if (!chip) return;
      const cmd = chip.getAttribute('data-cmd') || '';
      const file = chip.getAttribute('data-file') || '';
      if (file) activateTab(file);
      const box = $('commandInput');
      if (box) { box.value = cmd; box.focus(); }
      cancelSpeech();
      if (chip.closest('.ide-palette-overlay')) closeCommandPalette({ returnFocus: false });
      handleStudentText(cmd);
    });
    const openPaletteBtn = $('openPaletteBtn');
    if (openPaletteBtn) openPaletteBtn.addEventListener('click', openCommandPalette);
    const closePaletteBtn = $('closePaletteBtn');
    if (closePaletteBtn) closePaletteBtn.addEventListener('click', () => closeCommandPalette());
    const paletteOverlay = $('paletteOverlay');
    if (paletteOverlay) paletteOverlay.addEventListener('click', (event) => {
      if (event.target === paletteOverlay) closeCommandPalette();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && isPaletteOpen()) { event.preventDefault(); closeCommandPalette(); return; }
      paletteTrapFocus(event);
    });

    setupTabs();
    ensureEditors();
    ensurePreviewFrame();
    renderPythonInputs();
    renderPythonHistory();
    restoreLocalFeatureState();
    refreshSnippetSelect();
    updateTutorialPanel();
    window.runCode = () => previewHtml(true);
    window.runPythonCode = runPythonCode;
    window.analyzePythonCode = analyzePythonCode;
    window.pythonAudioCodeMap = pythonAudioCodeMap;
    window.pythonStepNarration = pythonStepNarration;
    window.pythonWatchVariable = pythonWatchVariable;
    window.pythonConditionalBreakpoint = pythonConditionalBreakpoint;
    window.pythonStateWatch = pythonStateWatch;
    window.runPythonWithInputs = runPythonWithInputs;
    window.pythonMistakeReplay = pythonMistakeReplay;
    window.loadPythonExample = loadPythonExample;
    window.analyzeCode = analyzeCode;
    window.explainWebsite = explainWebsite;
    window.fixCode = applyAllAuditFixes;
    window.polishHtml = polishHtml;
    window.reviewWebsite = reviewWebsite;
    window.applyReviewSuggestion = (instruction) => applyReviewSuggestion(instruction, true);
    window.auditWebsite = auditWebsite;
    window.outlineWebsite = outlineWebsite;
    window.exportHtml = exportHtml;
    window.stepNarration = stepNarration;
    window.explainProjectFile = explainProjectFile;
    window.learningNotes = learningNotes;
    window.accessibilityMap = accessibilityMap;
    window.reviewProject = reviewProject;
    window.describePreview = describePreview;
    window.projectSummary = projectSummary;
    window.resetSession = resetSession;
    window.createNamedProject = createNamedProject;
    window.openSelectedProject = openSelectedProject;
    window.applyFirstAuditFix = applyFirstAuditFix;
    window.applyAllAuditFixes = applyAllAuditFixes;
    window.generateCode = (prompt) => buildWebsite(prompt, true);
    window.chatWithAI = (message) => chatWithAI(message, true);
    window.submitCommand = submitCommandFromInput;
    window.toggleVoice = toggleVoice;
    window.pauseVoiceRecognition = pauseVoice;
    window.resumeVoiceRecognition = resumeVoice;
    window.setWakeWord = (value) => {
      state.wakeWord = String(value || 'hey codeup').toLowerCase();
      localStorage.setItem('codeup_wake_word', state.wakeWord);
      writeOutput(`Wake word changed to ${state.wakeWord}.`, true);
    };
    window.setVoiceLangMode = (mode) => {
      if (window.VoiceMemoryEngine) {
        window.VoiceMemoryEngine.setVoiceLangMode(mode);
        localStorage.setItem('codeup_voice_lang_mode', mode);
        if (state.activeVoice && !state.paused) {
          stopActiveRecognition();
          setTimeout(startActiveRecognition, 200);
        }
      }
    };

    document.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'm') {
        event.preventDefault();
        toggleVoice();
      }
      if (event.key === 'Escape') cancelSpeech();
    }, true);
    $('languageSelector')?.addEventListener('change', () => {
      cancelSpeech();
      if (state.activeVoice && !state.paused) {
        stopActiveRecognition();
        setTimeout(startActiveRecognition, 300);
      } else if (state.wakeListening) {
        stopWakeListener();
        setTimeout(startWakeListener, 300);
      }
    });
    $('colorVisionMode')?.addEventListener('change', function () {
      const mode = this.value;
      document.body.classList.remove('cvd-protanopia', 'cvd-deuteranopia', 'cvd-tritanopia', 'cvd-high-contrast');
      if (mode !== 'default') document.body.classList.add('cvd-' + mode);
    });
    $('nightToggle')?.addEventListener('click', function () {
      const active = document.body.classList.toggle('theme-night');
      this.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    $('dyslexiaToggle')?.addEventListener('click', function () {
      const active = document.body.classList.toggle('theme-dyslexia');
      this.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    $('motionToggle')?.addEventListener('click', function () {
      const active = document.body.classList.toggle('theme-reduced-motion');
      this.setAttribute('aria-pressed', active ? 'true' : 'false');
    });
    $('demoModeBtn')?.addEventListener('click', toggleDemoMode);
    $('projectSaveBtn')?.addEventListener('click', renameProject);
    $('projectNewBtn')?.addEventListener('click', createNamedProject);
    $('projectDuplicateBtn')?.addEventListener('click', duplicateCurrentProject);
    $('projectOpenBtn')?.addEventListener('click', openSelectedProject);
    $('projectSelect')?.addEventListener('change', openSelectedProject);
    $('projectNameInput')?.addEventListener('change', renameProject);
    $('auditFixOneBtn')?.addEventListener('click', applyFirstAuditFix);
    $('auditFixAllBtn')?.addEventListener('click', applyAllAuditFixes);

    document.addEventListener('keydown', (event) => {
      if (event.altKey && event.key.toLowerCase() === 'b') {
        event.preventDefault();
        breadcrumb();
      }
    });

    $('snippetSelect')?.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') { event.preventDefault(); loadSnippetFromUi(); }
    });
  }

  function updateStateIndicator(voiceState) {
    const button = $('voiceButton');
    if (!button) return;
    const indicator = voiceState || 'IDLE';
    button.dataset.voiceState = indicator;
    const sr = $('srAnnouncer');
    if (indicator === 'PROCESSING' && sr) sr.textContent = t('Processing...', 'Process ho raha hai...');
    if (indicator === 'RESPONDING' && sr) sr.textContent = t('AI is responding...', 'AI jawab de raha hai...');
    if (indicator === 'SPEAKING' && sr) sr.textContent = t('Speaking response...', 'Jawab bol raha hai...');
  }

  function initVoiceMemoryEngine() {
    if (!window.VoiceMemoryEngine) return;
    const VME = window.VoiceMemoryEngine;

    const savedLangMode = localStorage.getItem('codeup_voice_lang_mode');
    if (savedLangMode) VME.setVoiceLangMode(savedLangMode);

    let lastRenderedText = '';

    VME.onStateChange = function (newState, prevState) {
      updateStateIndicator(newState);
      const output = $('output');
      if (newState === 'LISTENING' && output) {
        if (prevState === 'SPEAKING' || prevState === 'RESPONDING') {
          output.classList.add('cu-fade-in');
          output.textContent = t('Listening...', 'Sun raha hoon...');
          output.classList.remove('cu-streaming', 'cu-typing');
          setTimeout(() => output.classList.remove('cu-fade-in'), 300);
        }
        if (state.activeVoice && !state.paused && !state.manualVoiceStop && !state.activeRecognition) {
          setTimeout(startActiveRecognition, 100);
        }
      }
      if (newState === 'PROCESSING' && output) {
        output.classList.add('cu-fade-in');
        output.textContent = t('Thinking...', 'Soch raha hoon...');
        output.classList.remove('cu-streaming', 'cu-typing');
        setTimeout(() => output.classList.remove('cu-fade-in'), 300);
        lastRenderedText = '';
      }
      if (newState === 'RESPONDING' && output) {
        output.classList.add('cu-streaming', 'cu-typing');
      }
      if (newState === 'IDLE' && output) {
        output.classList.remove('cu-streaming', 'cu-typing', 'cu-fade-in');
      }
    };

    VME.onStreamChunk = function (fullText, spokenIndex) {
      const output = $('output');
      if (!output) return;
      const display = fullText.slice(-2000);
      if (display !== lastRenderedText) {
        output.textContent = display;
        output.scrollTop = output.scrollHeight;
        lastRenderedText = display;
      }
    };

    VME.onSyncUpdate = function (spokenIdx, renderedIdx) {
    };

    VME.onResponseComplete = function (response, prompt) {
      const output = $('output');
      if (output) {
        output.classList.remove('cu-typing');
      }
    };

    VME.onError = function (error) {
      writeOutput(error.message || t('An error occurred.', 'Ek error aayi.'), true);
      updateStateIndicator('IDLE');
    };
  }

  const originalHandleVoiceCommand = handleVoiceCommand;
  async function handleVoiceCommandWithInterrupt(raw) {
    const command = raw.trim();
    if (!command) return;
    const lower = command.toLowerCase();
    if (shouldUsePythonStateWatch(lower)) {
      await originalHandleVoiceCommand(command);
      return;
    }
    if (isTutorialControlCommand(lower)) {
      await handleTutorialCommand(command);
      return;
    }
    if (window.VoiceMemoryEngine) {
      if (!window.VoiceMemoryEngine.handleTranscript(command)) {
        return;
      }
    }
    await originalHandleVoiceCommand(command);
    if (isMacroWorthyCommand(command)) {
      state.lastCommand = command;
    }
    if (shouldValidateTutorialCommand(lower)) await validateTutorialProgress(command);
    if (state.track && state.track.active && state.track.guided && !isTutorialControlCommand(lower)) await validateGuidedProgress();
  }

  if (window.__codeupEnableTestHooks) {
    window.__codeupVoiceTest = {
      state,
      startVoice,
      startWakeListener,
      stopVoice,
      pauseVoice,
      resumeVoice,
      toggleVoice,
      updateVoiceButton,
      applyCssEdit,
      undoByVoice,
      snapshotVersion,
      restoreVersions,
      setHtml,
      getHtml,
      getCss,
      getJs,
      getPython,
      editorValue,
      setEditorValue,
      upgradeEditorsWithMonaco,
      loadGeneratedFiles,
      combineDocument,
      splitDocument,
      saveSnippet,
      listSnippets,
      loadSnippet,
      loadSnippets,
      deleteSnippet,
      sonifyHtml,
      readCode,
      codeMap,
      stepNarration,
      runPythonCode,
      analyzePythonCode,
      pythonAudioCodeMap,
      pythonStepNarration,
      pythonWatchVariable,
      pythonConditionalBreakpoint,
      pythonStateWatch,
      runPythonWithInputs,
      pythonExplainError,
      pythonMistakeReplay,
      showPythonHistory,
      loadPythonExample,
      explainProjectFile,
      learningNotes,
      accessibilityMap,
      reviewProject,
      describePreview,
      projectSummary,
      landmarks,
      trainerNotes,
      studentRecap,
      screenReaderSummary,
      repairCommand,
      handleStudentText,
      handleTutorialCommand,
      validateTutorialProgress,
      saveMacro,
      runMacro,
      listMacros,
      deleteMacro,
      saveBookmark,
      readBookmark,
      listBookmarks,
      deleteBookmark,
      breadcrumb,
      explainErrors,
      narrateReplay,
      walkthroughCompare,
      checkWatchpoints,
      startHeartbeat,
      stopHeartbeat,
      stopEverything,
      handleIdeCommand,
      activateTab,
      openCommandPalette,
      closeCommandPalette,
      suggestNext,
      runWebsite,
      debugWebsite,
      debugFix,
      screenReaderTour,
      keyboardTest,
      visualDescription,
      readinessScore,
      teacherReview,
      showHistory,
      startTrack,
      trackNext,
      trackExit,
      selectorExplainer,
      pilotReport,
      startGuidedBuild,
      validateGuidedProgress,
      trackHint,
      trackRecap,
    };
  }

  window.addEventListener('load', async () => {
    await loadMemory();
    restoreVersions();
    setupUi();
    upgradeEditorsWithMonaco();
    state.pages.home = getHtml();
    await ensureProject();
    restoreLocalFeatureState();
    document.body.dataset.htmlModeReady = 'true';
    initVoiceMemoryEngine();
    if (!state.versions.length) snapshotVersion('Initial version');
    try { await previewHtml(false); } catch (e) {}
    setTimeout(startWakeListener, 600);
    speak(t(
      `CodeUp Web ready. Say ${state.wakeWord} to start voice commands, use the Voice button, or type what can I do here.`,
      `CodeUp Web ready hai. Voice commands start karne ke liye ${state.wakeWord} boliye, Voice button use karein, ya what can I do here type karein.`
    ));
  });
})();
