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
      color: #17202a;
      background: #f5f7fb;
    }
    header {
      padding: 56px 24px;
      color: white;
      background: linear-gradient(135deg, #0f766e, #2563eb);
      text-align: center;
    }
    main {
      max-width: 960px;
      margin: 0 auto;
      padding: 28px 20px;
    }
    section {
      margin: 18px 0;
      padding: 22px;
      border: 1px solid #d9e2ec;
      border-radius: 8px;
      background: white;
    }
    button {
      padding: 10px 14px;
      border: 0;
      border-radius: 6px;
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

  const state = {
    recognition: null,
    listening: false,
    paused: false,
    lastSpoken: '',
    lastUrl: '',
    memory: { history: [], last_html: '', last_url: '' },
    audioCtx: null,
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

  function speak(text, opts = {}) {
    if (!text) return;
    cancelSpeech();
    state.lastSpoken = text;
    announce(text);
    if (opts.silent) return;
    if (!('speechSynthesis' in window)) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = isHindi() ? 'hi-IN' : 'en-US';
    utterance.rate = opts.rate || 1;
    utterance.pitch = opts.pitch || 1;
    window.speechSynthesis.speak(utterance);
  }

  window.speak = speak;

  function writeOutput(message, shouldSpeak = false) {
    const output = $('output');
    if (output) output.textContent = message;
    if (shouldSpeak) speak(message);
  }

  function getEditor() { return $('htmlEditor'); }
  function getHtml() { return (getEditor() || {}).value || ''; }

  function setHtml(html) {
    const editor = getEditor();
    if (editor) {
      editor.value = html;
      try { sessionStorage.setItem('codeup_html_draft', html); } catch (error) {}
    }
  }

  function ensureHtmlEditor() {
    let editor = getEditor();
    if (editor) return editor;
    const host = $('editor');
    if (!host) return null;
    host.innerHTML = '';
    editor = document.createElement('textarea');
    editor.id = 'htmlEditor';
    editor.className = 'cu-html-editor';
    editor.spellcheck = false;
    editor.setAttribute('aria-label', 'HTML website editor. Dictate or type HTML, CSS, and JavaScript.');
    editor.value = sessionStorage.getItem('codeup_html_draft') || state.memory.last_html || starterHtml;
    editor.addEventListener('input', () => {
      try { sessionStorage.setItem('codeup_html_draft', editor.value); } catch (error) {}
    });
    editor.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
        event.preventDefault();
        previewHtml(true);
      }
      if (event.key === 'Escape') cancelSpeech();
    });
    host.appendChild(editor);
    return editor;
  }

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
      '<div class="cu-preview-toolbar">',
      '  <a id="sitePreviewLink" class="cu-button cu-button-secondary" href="#" target="_blank" rel="noopener">Open local site</a>',
      '</div>',
      '<iframe id="sitePreviewFrame" title="Student website preview" sandbox="allow-scripts allow-forms allow-modals"></iframe>',
    ].join('');
    if (preview !== wrapper) wrapper.appendChild(preview);
    return $('sitePreviewFrame');
  }

  async function saveMemory(payload) {
    try {
      const response = await fetch('/html-memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (data.success && data.memory) state.memory = data.memory;
    } catch (error) {}
  }

  async function loadMemory() {
    try {
      const response = await fetch('/html-memory');
      const data = await response.json();
      if (data.success && data.memory) state.memory = data.memory;
    } catch (error) {}
  }

  async function publish(html) {
    const response = await fetch('/publish-site', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ html }),
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error || 'Could not publish website.');
    state.lastUrl = data.url;
    state.memory.last_url = data.url;
    const frame = ensurePreviewFrame();
    if (frame) frame.src = data.url + '?t=' + Date.now();
    const link = $('sitePreviewLink');
    if (link) link.href = data.url;
    await saveMemory({ html, url: data.url, note: 'Published local preview' });
    return data.url;
  }

  async function previewHtml(shouldSpeak = false) {
    const html = getHtml();
    writeOutput(t('Publishing local preview...', 'Website local preview mein publish ho rahi hai...'));
    try {
      const url = await publish(html);
      const message = t(
        `Website is live locally at ${url}\nThe HTML is in the editor and the preview is below.`,
        `Website ready hai: ${url}\nHTML editor mein hai aur preview neeche dikh raha hai.`
      );
      writeOutput(message, shouldSpeak);
      announce('Website preview ready');
    } catch (error) {
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

  async function buildWebsite(prompt, shouldSpeak = true) {
    cancelSpeech();
    if (!prompt) {
      writeOutput(t(
        'Type or say a request like: Build a website for my school project.',
        'Request boliye ya likhiye: mere school project ke liye website banao.'
      ), true);
      return;
    }
    const normalized = /^build a website/i.test(prompt) || /^make/i.test(prompt)
      ? prompt
      : 'Build a website for ' + prompt;
    writeOutput(t('Building website...', 'Website ban rahi hai...'), shouldSpeak);
    try {
      const response = await fetch('/generate-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: normalized,
          language: lang(),
          current_html: getHtml(),
        }),
      });
      const data = await response.json();
      if (!data.success || !data.code) throw new Error(data.error || 'Website generation failed.');
      setHtml(data.code);
      const url = await publish(data.code);
      await saveMemory({ prompt: normalized, html: data.code, url });
      await explainWebsite(false);
      const message = t(
        `Website built and hosted locally at ${url}. I also wrote an explanation in the output panel.`,
        `Website ban gayi aur local URL ${url} par host ho gayi. Explanation output panel mein hai.`
      );
      if (shouldSpeak) speak(message);
    } catch (error) {
      writeOutput(error.message, true);
    }
  }

  async function polishHtml() {
    writeOutput(t('Polishing HTML...', 'HTML polish ho raha hai...'), true);
    try {
      const response = await fetch('/fix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: getHtml(), language: lang() }),
      });
      const data = await response.json();
      if (!data.success || !data.code) throw new Error(data.error || 'Could not polish the HTML.');
      setHtml(data.code);
      await publish(data.code);
      writeOutput(t('HTML polished and preview updated.', 'HTML polish ho gaya aur preview update ho gaya.'), true);
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

  function playTone(freq, duration, offset = 0, type = 'sine') {
    const ctx = ensureAudio();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.value = 0.045;
    osc.connect(gain);
    gain.connect(ctx.destination);
    const start = ctx.currentTime + offset;
    osc.start(start);
    gain.gain.exponentialRampToValueAtTime(0.001, start + duration);
    osc.stop(start + duration);
  }

  function sonifyHtml() {
    cancelSpeech();
    const html = getHtml();
    const tags = [...html.matchAll(/<\/?([a-zA-Z][\w-]*)\b[^>]*>/g)].map(match => match[1].toLowerCase());
    if (!tags.length) {
      speak(t('No HTML tags found to sonify.', 'Sonify karne ke liye HTML tags nahi mile.'));
      return;
    }
    speak(t(`Sonifying ${tags.length} HTML tags.`, `${tags.length} HTML tags ko sound mein suna raha hoon.`));
    tags.slice(0, 80).forEach((tag, index) => {
      const base = tag === 'header' ? 520 : tag === 'section' ? 440 : tag === 'button' ? 700 : tag === 'img' ? 820 : tag === 'script' ? 300 : 360;
      playTone(base + (index % 5) * 35, 0.12, index * 0.11, tag === 'button' ? 'square' : 'sine');
    });
  }

  function insertAtCursor(text) {
    const editor = getEditor();
    if (!editor) return;
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const before = editor.value.slice(0, start);
    const after = editor.value.slice(end);
    editor.value = before + text + after;
    editor.selectionStart = editor.selectionEnd = start + text.length;
    editor.focus();
    try { sessionStorage.setItem('codeup_html_draft', editor.value); } catch (error) {}
  }

  function addHtmlFromSpeech(command) {
    const lower = command.toLowerCase();
    const heading = command.match(/(?:add|insert|write|heading|title|sheershak|heading)\s+(?:heading\s+|title\s+)?(.+)/i);
    const paragraph = command.match(/(?:add paragraph|insert paragraph|write paragraph|paragraph|para|anuched)\s+(.+)/i);
    const button = command.match(/(?:add button|insert button|button|button jodo)\s+(.+)/i);
    if (button) {
      insertAtCursor(`\n<button type="button">${button[1].trim()}</button>\n`);
      speak(t('Button added.', 'Button add ho gaya.'));
      return true;
    }
    if (paragraph) {
      insertAtCursor(`\n<p>${paragraph[1].trim()}</p>\n`);
      speak(t('Paragraph added.', 'Paragraph add ho gaya.'));
      return true;
    }
    if (heading && !lower.includes('website')) {
      insertAtCursor(`\n<h2>${heading[1].trim()}</h2>\n`);
      speak(t('Heading added.', 'Heading add ho gayi.'));
      return true;
    }
    return false;
  }

  function helpText() {
    return t(
      'You can say: build a website for robotics club, preview website, explain website, sonify website, polish HTML, add heading About Us, add paragraph Welcome students, pause voice, resume voice, or stop speaking.',
      'Aap bol sakte hain: robotics club ke liye website banao, preview website, website samjhao, website sonify karo, HTML polish karo, heading add karo About Us, paragraph add karo Welcome students, pause voice, resume voice, ya stop speaking.'
    );
  }

  function isBuildIntent(text) {
    const lower = text.toLowerCase();
    return (
      /\b(build|make|create|generate)\b.*\b(website|site|page|webpage)\b/i.test(text) ||
      /\b(website|site|page|webpage)\s+for\b/i.test(text) ||
      /\b(banao|bana do|banaiye|banaye|banaao)\b/i.test(lower)
    );
  }

  async function handleVoiceCommand(raw) {
    const command = raw.trim();
    if (!command) return;
    cancelSpeech();
    const lower = command.toLowerCase();
    writeOutput(`${t('Heard', 'Suna')}: ${command}`);

    if (lower.includes('pause voice') || lower.includes('stop listening') || lower.includes('awaaz rok') || lower.includes('ruk jao')) {
      pauseVoice();
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
    if (lower.includes('help') || lower.includes('madad')) {
      await chatWithAI(command, true);
      return;
    }
    if (lower.includes('preview') || lower.includes('show website') || lower.includes('run website') || lower.includes('dikhao')) {
      await previewHtml(true);
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

    const buildMatch = command.match(/(?:build|make|create|banao|bana do|website for|ke liye website)\s+(.+)/i);
    if (buildMatch || isBuildIntent(command)) {
      await buildWebsite(buildMatch ? buildMatch[1] : command, true);
      return;
    }
    await chatWithAI(command, true);
  }

  async function handleStudentText(raw) {
    const text = raw.trim();
    if (!text) {
      await chatWithAI(text, true);
      return;
    }
    const lower = text.toLowerCase();
    const isBuildRequest = isBuildIntent(text);
    if (isBuildRequest) {
      await handleVoiceCommand(text);
      return;
    }
    if (
      lower.includes('preview') ||
      lower.includes('explain') ||
      lower.includes('describe') ||
      lower.includes('sonify') ||
      lower.includes('polish') ||
      lower.includes('pause voice') ||
      lower.includes('resume voice') ||
      lower.includes('stop speaking') ||
      lower.includes('add heading') ||
      lower.includes('add paragraph') ||
      lower.includes('add button')
    ) {
      await handleVoiceCommand(text);
      return;
    }
    await chatWithAI(text, true);
  }

  function startVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      speak(t('Voice recognition is not supported in this browser. Please use Chrome or Edge.', 'Is browser mein voice recognition support nahi hai. Chrome ya Edge use karein.'));
      return;
    }
    if (state.listening) {
      speak(t('Voice is already on.', 'Voice pehle se on hai.'));
      return;
    }
    cancelSpeech();
    state.recognition = new SpeechRecognition();
    state.recognition.continuous = true;
    state.recognition.interimResults = false;
    state.recognition.lang = isHindi() ? 'hi-IN' : 'en-US';
    state.recognition.onstart = () => {
      state.listening = true;
      state.paused = false;
      updateVoiceButton();
      speak(t('Voice on. You can code hands free.', 'Voice on hai. Aap bina keyboard ke code kar sakte hain.'));
    };
    state.recognition.onresult = (event) => {
      cancelSpeech();
      const result = event.results[event.results.length - 1];
      const transcript = result && result[0] ? result[0].transcript : '';
      handleVoiceCommand(transcript);
    };
    state.recognition.onerror = () => updateVoiceButton();
    state.recognition.onend = () => {
      const shouldRestart = state.listening;
      if (shouldRestart) {
        setTimeout(() => {
          try { state.recognition.start(); } catch (error) {}
        }, 400);
      }
    };
    try { state.recognition.start(); } catch (error) { speak(t('Could not start voice.', 'Voice start nahi ho payi.')); }
  }

  function stopVoice() {
    state.listening = false;
    state.paused = false;
    try { if (state.recognition) state.recognition.stop(); } catch (error) {}
    updateVoiceButton();
    speak(t('Voice off.', 'Voice off hai.'));
  }

  function pauseVoice() {
    state.paused = true;
    updateVoiceButton();
    speak(t('Voice paused. Say resume voice when you want commands again.', 'Voice pause hai. Dobara command ke liye resume voice boliye.'));
  }

  function resumeVoice() {
    state.paused = false;
    updateVoiceButton();
    speak(t('Voice resumed.', 'Voice resume ho gayi.'));
  }

  function toggleVoice() {
    if (state.listening) stopVoice();
    else startVoice();
  }

  function updateVoiceButton() {
    const button = $('voiceButton');
    if (!button) return;
    button.classList.toggle('cu-button-voice--active', state.listening && !state.paused);
    button.classList.toggle('cu-button-voice--paused', state.paused);
    button.setAttribute('aria-pressed', state.listening ? 'true' : 'false');
    button.textContent = state.paused
      ? 'Voice Paused'
      : state.listening
        ? 'Voice On'
        : 'Voice Off';
  }

  function setupUi() {
    document.title = 'CodeUp HTML - Blind-first Website Builder';
    const pageTitle = document.querySelector('.cu-title');
    if (pageTitle) pageTitle.textContent = 'CODEUP HTML';
    const status = document.querySelector('.cu-status-pill');
    if (status) {
      status.textContent = 'HTML + VOICE';
      status.setAttribute('aria-label', 'HTML website builder with voice');
    }
    const subtitle = document.querySelector('.cu-subtitle');
    if (subtitle) subtitle.innerHTML = 'Blind-first HTML website builder. Press <span class="cu-hotkey">Ctrl+Enter</span> to preview.';
    const info = document.querySelector('.cu-subtitle-info small');
    if (info) info.textContent = 'Voice coding - Hindi and English - sonification - local website hosting';

    replaceButton('runBtn', 'Preview', 'Preview HTML website', () => previewHtml(true));
    replaceButton('analyzeBtn', 'Explain', 'Explain what the website looks like', () => explainWebsite(true));
    replaceButton('fixBtn', 'Polish', 'Polish HTML accessibility and layout', polishHtml);
    replaceButton('voiceButton', 'Voice Off', 'Toggle voice control', toggleVoice);
    replaceButton('tutorialBtn', 'Help', 'Hear HTML voice commands', () => writeOutput(helpText(), true));
    replaceButton('helpBtn', 'Help', 'Hear HTML voice commands', () => writeOutput(helpText(), true));
    replaceButton('sendCommandBtn', 'Ask / Build', 'Ask CodeUp or build a website from request', () => {
      const field = $('voiceText') || $('commandInput');
      const value = field ? field.value.trim() : '';
      if (field) field.value = '';
      handleStudentText(value);
    });

    const label = $('command-input-label');
    if (label) label.textContent = 'WEBSITE REQUEST OR VOICE TRANSCRIPT';
    const field = $('voiceText') || $('commandInput');
    if (field) {
      field.placeholder = 'Ask what you can do, or build a website for a school science fair...';
      field.setAttribute('aria-label', 'Website request or voice transcript');
      const clone = field.cloneNode(true);
      field.replaceWith(clone);
      clone.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        cancelSpeech();
        const value = clone.value.trim();
        clone.value = '';
        handleStudentText(value);
      });
    }

    const structure = $('structurePanel');
    if (structure) {
      structure.hidden = true;
      structure.style.display = 'none';
    }
    const startGate = $('startGate');
    if (startGate) startGate.remove();
    const inputsPanel = $('inputAddField');
    if (inputsPanel) {
      const secondTitle = inputsPanel.closest('.cu-snippets')?.querySelectorAll('.cu-panel-title')[1];
      if (secondTitle) secondTitle.textContent = 'SESSION MEMORY';
      const wrapper = inputsPanel.closest('div');
      if (wrapper) wrapper.style.display = 'none';
    }
    ['inputsPanelList', 'clearInputsBtn', 'toggleInputModeBtn', 'inputModeIndicator'].forEach(id => {
      const el = $(id);
      if (el) el.style.display = 'none';
    });

    ensureHtmlEditor();
    ensurePreviewFrame();
    window.runCode = () => previewHtml(true);
    window.analyzeCode = () => explainWebsite(true);
    window.fixCode = polishHtml;
    window.generateCode = (prompt) => buildWebsite(prompt, true);
    window.chatWithAI = (message) => chatWithAI(message, true);
    window.submitCommand = async () => {
      const field = $('voiceText') || $('commandInput');
      const value = field ? field.value.trim() : '';
      if (field) field.value = '';
      await handleStudentText(value);
    };
    window.toggleVoice = toggleVoice;
    window.pauseVoiceRecognition = pauseVoice;
    window.resumeVoiceRecognition = resumeVoice;

    document.addEventListener('keydown', (event) => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'm') {
        event.preventDefault();
        toggleVoice();
      }
      if (event.key === 'Escape') cancelSpeech();
    }, true);
    document.addEventListener('click', (event) => {
      const button = event.target && event.target.closest ? event.target.closest('button') : event.target;
      if (!button || !button.id) return;
      if (button.id === 'sendCommandBtn') {
        event.preventDefault();
        event.stopImmediatePropagation();
        const field = $('voiceText') || $('commandInput');
        const value = field ? field.value.trim() : '';
        if (field) field.value = '';
        handleStudentText(value);
      }
    }, true);
    $('languageSelector')?.addEventListener('change', () => {
      cancelSpeech();
      if (state.listening && state.recognition) {
        stopVoice();
        setTimeout(startVoice, 300);
      }
    });

    document.body.dataset.htmlModeReady = 'true';
  }

  window.addEventListener('load', async () => {
    await loadMemory();
    setupUi();
    await previewHtml(false);
    speak(t(
      'CodeUp HTML ready. Turn on voice to build websites in English or Hindi.',
      'CodeUp HTML ready hai. Hindi ya English mein website banane ke liye voice on karein.'
    ));
  });
})();
