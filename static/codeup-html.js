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
    activeRecognition: null,
    wakeRecognition: null,
    activeVoice: false,
    wakeListening: false,
    paused: false,
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

  function slugify(value) {
    return (value || 'codeup-site').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'codeup-site';
  }

  function getEditor() { return $('htmlEditor'); }
  function getHtml() { return (getEditor() || {}).value || ''; }

  function snapshotVersion(note) {
    const html = getHtml();
    if (!html) return;
    const last = state.versions[state.versions.length - 1];
    if (last && last.html === html) return;
    state.versions.push({
      html,
      note: note || 'Edited website',
      page: state.currentPage,
      timestamp: new Date().toISOString(),
    });
    state.versions = state.versions.slice(-25);
    persistVersions();
  }

  function setHtml(html) {
    const editor = getEditor();
    if (editor) {
      editor.value = html;
      try { sessionStorage.setItem('codeup_html_draft', html); } catch (error) {}
      state.pages[state.currentPage] = html;
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
      state.pages[state.currentPage] = editor.value;
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
    const activePages = Object.fromEntries(Object.entries(state.pages).filter(([, value]) => value && value.trim()));
    const payload = Object.keys(activePages).length > 1 ? { html, pages: activePages } : { html };
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
    const link = $('sitePreviewLink');
    if (link) link.href = data.url;
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
    speak('Created a homepage, about page, and contact page. You are editing the homepage.');
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

  function exportHtml() {
    const html = getHtml();
    const title = (html.match(/<title>\s*([^<]+)/i) || [])[1] || 'codeup-site';
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = slugify(title) + '.html';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 500);
    writeOutput(t('HTML file exported.', 'HTML file export ho gayi.'), true);
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
    const color = findColor();
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
    const html = getHtml();
    setHtml(injectVoiceCss(html, rules));
    writeOutput(`Applied CSS edit: ${rules.join(' ')}`, true);
    previewHtml(false);
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

  function undoByVoice(command) {
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
    state.versions = state.versions.slice(0, target + 1);
    persistVersions();
    setHtml(version.html);
    writeOutput(`Restored version: ${version.note}.`, true);
    return true;
  }

  function reviewChanges() {
    if (state.versions.length < 2) {
      speak('There is only one saved version so far.');
      return true;
    }
    const previous = _htmlWords(state.versions[state.versions.length - 2].html);
    const current = _htmlWords(state.versions[state.versions.length - 1].html);
    const added = [...current].filter(word => !previous.has(word)).slice(0, 8);
    const removed = [...previous].filter(word => !current.has(word)).slice(0, 8);
    const message = `Changed since the last version. Added: ${added.join(', ') || 'nothing major'}. Removed: ${removed.join(', ') || 'nothing major'}.`;
    writeOutput(message, true);
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
    try { sessionStorage.removeItem('codeup_html_draft'); } catch (error) {}
    setHtml(starterHtml);
    const frame = $('sitePreviewFrame');
    if (frame) frame.removeAttribute('src');
    const link = $('sitePreviewLink');
    if (link) link.href = '#';
    writeOutput(t('Session reset. Starter website loaded.', 'Session reset ho gaya. Starter website load ho gayi.'), true);
  }

  async function auditWebsite(shouldSpeak = true) {
    writeOutput(t('Auditing accessibility...', 'Accessibility audit chal raha hai...'), shouldSpeak);
    try {
      const response = await fetch('/html-audit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html: getHtml() }),
      });
      const data = await response.json();
      if (!data.success) throw new Error(data.error || 'Audit failed.');
      const audit = data.audit;
      const checks = audit.checks.map(item => `${item.passed ? 'PASS' : 'FIX'} - ${item.label}`).join('\n');
      const suggestions = audit.suggestions.map(item => `- ${item}`).join('\n');
      const contrast = (audit.contrast_pairs || []).map(item => `${item.passes_aa ? 'PASS' : 'FIX'} - ${item.selector}: ${item.ratio}:1`).join('\n');
      const transcript = (audit.screen_reader_transcript || []).slice(0, 12).map(item => `- ${item.announcement}`).join('\n');
      const message = `Accessibility score: ${audit.score}/100\n\n${checks}\n\nContrast:\n${contrast || 'No color pairs found.'}\n\nScreen reader transcript preview:\n${transcript || 'No readable announcements found.'}\n\nSuggestions:\n${suggestions}`;
      writeOutput(message, shouldSpeak);
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
        }),
      });
      const data = await response.json();
      if (!data.success || !data.code) throw new Error(data.error || 'Could not apply review suggestions.');
      snapshotVersion('Before applying review');
      setHtml(data.code);
      if (data.memory) state.memory = data.memory;
      const url = await publish(data.code);
      const nextReview = await reviewWebsite(false);
      const message = t(
        `I added the review improvements, republished the website at ${url}, and reviewed the new version. ${nextReview}`,
        `Review improvements add ho gaye, website ${url} par republish ho gayi, aur naya version review ho gaya. ${nextReview}`
      );
      if (shouldSpeak) speak(message);
    } catch (error) {
      writeOutput(error.message, true);
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

    if (window.VoiceMemoryEngine && shouldSpeak) {
      writeOutput(t('Building website...', 'Website ban rahi hai...'));
      updateStateIndicator('PROCESSING');
      const result = await window.VoiceMemoryEngine.streamAIResponse(normalized, {
        currentHtml: getHtml(),
      });
      if (result) {
        const html = result.indexOf('<') !== -1 ? result : '';
        if (html) {
          snapshotVersion('Before building website');
          state.currentPage = 'home';
          state.pages = {};
          setHtml(html);
          snapshotVersion('Built website');
          try {
            const url = await publish(html);
            await saveMemory({ prompt: normalized, html, url });
            const review = await reviewWebsite(false);
            writeOutput(t(
              `Website built and hosted locally at ${url}. ${review}`,
              `Website ban gayi: ${url}. ${review}`
            ), false);
          } catch (error) {
            writeOutput(t('Website built but preview failed.', 'Website bani par preview fail.'), false);
          }
        }
      }
      return;
    }

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
      snapshotVersion('Before building website');
      state.currentPage = 'home';
      state.pages = {};
      setHtml(data.code);
      snapshotVersion('Built website');
      const url = await publish(data.code);
      await saveMemory({ prompt: normalized, html: data.code, url });
      const review = await reviewWebsite(false);
      const message = t(
        `Website built and hosted locally at ${url}. Here is the first review. ${review}`,
        `Website ban gayi aur local URL ${url} par host ho gayi. Pehla review yeh hai. ${review}`
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
      snapshotVersion('Before polishing HTML');
      setHtml(data.code);
      snapshotVersion('Polished HTML');
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

  function sonifyHtml() {
    cancelSpeech();
    const html = getHtml();
    const doc = previewDocument();
    const elements = [...doc.body.querySelectorAll('header,main,section,article,nav,h1,h2,h3,p,a,button,img,form')];
    const tags = elements.length
      ? elements.map((node, index) => ({ tag: node.tagName.toLowerCase(), pan: (index % 5 - 2) / 2 }))
      : [...html.matchAll(/<\/?([a-zA-Z][\w-]*)\b[^>]*>/g)].map((match, index) => ({ tag: match[1].toLowerCase(), pan: (index % 5 - 2) / 2 }));
    if (!tags.length) {
      speak(t('No HTML tags found to sonify.', 'Sonify karne ke liye HTML tags nahi mile.'));
      return;
    }
    speak(t(`Sonifying ${tags.length} HTML tags.`, `${tags.length} HTML tags ko sound mein suna raha hoon.`));
    tags.slice(0, 80).forEach((item, index) => {
      const tag = item.tag;
      const base = tag === 'header' ? 520 : tag === 'section' ? 440 : tag === 'button' ? 700 : tag === 'img' ? 820 : tag === 'script' ? 300 : 360;
      playTone(base + (index % 5) * 35, 0.12, index * 0.11, tag === 'button' ? 'square' : 'sine', item.pan);
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
      snapshotVersion('Before adding button');
      insertAtCursor(`\n<button type="button">${button[1].trim()}</button>\n`);
      speak(t('Button added.', 'Button add ho gaya.'));
      return true;
    }
    if (paragraph) {
      snapshotVersion('Before adding paragraph');
      insertAtCursor(`\n<p>${paragraph[1].trim()}</p>\n`);
      speak(t('Paragraph added.', 'Paragraph add ho gaya.'));
      return true;
    }
    if (heading && !lower.includes('website')) {
      snapshotVersion('Before adding heading');
      insertAtCursor(`\n<h2>${heading[1].trim()}</h2>\n`);
      speak(t('Heading added.', 'Heading add ho gayi.'));
      return true;
    }
    return false;
  }

  function helpText() {
    return t(
      'You can say: build a website for robotics club, preview website, what is missing, review website, add that, explain website, audit website, outline website, export website, reset session, sonify website, polish HTML, add heading About Us, add paragraph Welcome students, pause voice, resume voice, or stop speaking.',
      'Aap bol sakte hain: robotics club ke liye website banao, preview website, website samjhao, audit website, outline website, export website, reset session, website sonify karo, HTML polish karo, heading add karo About Us, paragraph add karo Welcome students, pause voice, resume voice, ya stop speaking. Hindi examples: school annual day ke liye website banao. Website kaisi dikhti hai? Isme kya missing hai? Add that.'
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

  async function handleVoiceCommand(raw) {
    const command = raw.trim();
    if (!command) return;
    cancelSpeech();
    const lower = command.toLowerCase();
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

    if (lower.includes('voice off') || lower.includes('stop voice')) {
      stopVoice();
      return;
    }
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
      undoByVoice(command);
      return;
    }
    if (lower.includes('what changed') || lower.includes('compare versions') || lower.includes('review changes')) {
      snapshotVersion('Current version for comparison');
      reviewChanges();
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
      exportHtml();
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
    state.wakeUntil = Date.now() + 45000;
    const lower = text.toLowerCase();
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
      lower.includes('center')
    ) {
      await handleVoiceCommand(text);
      return;
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
    if (!state.activeVoice || state.paused || state.activeRecognition) return;
    const recognition = new SpeechRecognition();
    state.activeRecognition = recognition;
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = isHindi() ? 'hi-IN' : 'en-US';
    recognition.onstart = () => {
      updateVoiceButton();
      announce(t('Voice command listening.', 'Voice command sun raha hai.'));
    };
    recognition.onresult = (event) => {
      cancelSpeech();
      handleVoiceCommandWithInterrupt(transcriptFromEvent(event));
    };
    recognition.onerror = () => updateVoiceButton();
    recognition.onend = () => {
      if (state.activeRecognition !== recognition) return;
      state.activeRecognition = null;
      updateVoiceButton();
      if (state.activeVoice && !state.paused) {
        setTimeout(() => {
          startActiveRecognition();
        }, 400);
      }
    };
    try {
      recognition.start();
    } catch (error) {
      if (state.activeRecognition === recognition) state.activeRecognition = null;
      state.activeVoice = false;
      state.paused = false;
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
    state.wakeUntil = Date.now() + 45000;
    updateVoiceButton();
    startActiveRecognition();
    if (!options.silent) {
      speak(t('Voice on. You can code hands free.', 'Voice on hai. Aap bina keyboard ke code kar sakte hain.'));
    }
  }

  function startWakeListener() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition || state.wakeListening || (state.activeVoice && !state.paused)) return;
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
    stopActiveRecognition();
    updateVoiceButton();
    startWakeListener();
    if (wasActive) speak(t('Voice off.', 'Voice off hai.'));
  }

  function pauseVoice() {
    if (!state.activeVoice) {
      writeOutput(t('Voice is already off.', 'Voice pehle se off hai.'), true);
      return;
    }
    state.paused = true;
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
  }

  async function submitCommandFromInput() {
    const field = $('commandInput');
    const value = field ? field.value.trim() : '';
    if (field) field.value = '';
    await handleStudentText(value);
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
    replaceButton('auditBtn', 'Audit', 'Audit accessibility and page quality', () => auditWebsite(true));
    replaceButton('outlineBtn', 'Outline', 'Summarize the website outline', () => outlineWebsite(true));
    replaceButton('exportBtn', 'Export', 'Export website as an HTML file', exportHtml);
    replaceButton('resetBtn', 'Reset', 'Reset this session', resetSession);
    replaceButton('voiceButton', 'Voice Off', 'Toggle voice control', toggleVoice);
    replaceButton('helpBtn', 'Help', 'Hear HTML voice commands', () => writeOutput(helpText(), true));
    replaceButton('sendCommandBtn', 'Ask / Build', 'Ask CodeUp or build a website from request', submitCommandFromInput);

    const field = $('commandInput');
    if (field) {
      field.placeholder = 'Ask what you can do, or build a website for a school science fair...';
      field.setAttribute('aria-label', 'Website request or voice transcript');
      const clone = field.cloneNode(true);
      field.replaceWith(clone);
      clone.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        cancelSpeech();
        submitCommandFromInput();
      });
    }

    ensureHtmlEditor();
    ensurePreviewFrame();
    window.runCode = () => previewHtml(true);
    window.analyzeCode = () => explainWebsite(true);
    window.fixCode = polishHtml;
    window.reviewWebsite = reviewWebsite;
    window.applyReviewSuggestion = (instruction) => applyReviewSuggestion(instruction, true);
    window.auditWebsite = auditWebsite;
    window.outlineWebsite = outlineWebsite;
    window.exportHtml = exportHtml;
    window.resetSession = resetSession;
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
    $('demoModeBtn')?.addEventListener('click', toggleDemoMode);

    document.body.dataset.htmlModeReady = 'true';
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

    VME.onStateChange = function (newState) {
      updateStateIndicator(newState);
    };

    VME.onStreamChunk = function (fullText) {
      const output = $('output');
      if (output) {
        output.textContent = fullText.slice(-2000);
        output.scrollTop = output.scrollHeight;
      }
    };

    VME.onResponseComplete = function (response, prompt) {
      updateStateIndicator('IDLE');
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
    if (window.VoiceMemoryEngine) {
      if (!window.VoiceMemoryEngine.handleTranscript(command)) {
        return;
      }
    }
    await originalHandleVoiceCommand(command);
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
    };
  }

  window.addEventListener('load', async () => {
    await loadMemory();
    restoreVersions();
    setupUi();
    initVoiceMemoryEngine();
    state.pages.home = getHtml();
    snapshotVersion('Initial version');
    await previewHtml(false);
    setTimeout(startWakeListener, 600);
    speak(t(
      `CodeUp HTML ready. Say ${state.wakeWord} to start voice commands, or use the Voice button.`,
      `CodeUp HTML ready hai. Voice commands start karne ke liye ${state.wakeWord} boliye, ya Voice button use karein.`
    ));
  });
})();
