"use strict";

(function () {
  const starterFiles = {
    html: `<!doctype html>
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
    <p>Describe a website above, then edit these files.</p>
    <button id="cta" type="button">Say hello</button>
  </header>
  <main>
    <section>
      <h2>About</h2>
      <p>This page uses HTML for structure, CSS for style, and JavaScript for behavior.</p>
    </section>
  </main>
  <script src="script.js" defer></script>
</body>
</html>`,
    css: `body { margin: 0; font-family: system-ui, sans-serif; line-height: 1.6; color: #111827; background: #ffffff; }
.site-header { padding: 24px; border-bottom: 1px solid #d1d5db; background: #f9fafb; }
main { max-width: 820px; margin: 0 auto; padding: 24px 20px; }
button { font: inherit; padding: 9px 14px; border: 1px solid #1d4ed8; color: white; background: #1d4ed8; }
button:focus-visible, a:focus-visible { outline: 3px solid #f59e0b; outline-offset: 3px; }`,
    js: `const cta = document.getElementById("cta");
if (cta) {
  cta.addEventListener("click", () => {
    cta.textContent = "Hello from JavaScript";
  });
}`,
  };

  const helpGroups = {
    Build: ["make a portfolio website", "make a website for my robotics club", "make a quiz app"],
    Edit: ["add an about section", "change the title", "make it simpler", "add a contact form"],
    Understand: ["explain HTML", "explain CSS", "explain JavaScript", "code map", "describe preview", "what changed"],
    "Test and improve": ["run website", "debug website", "check accessibility", "fix accessibility issues", "is this ready to share"],
    Project: ["save project", "open project", "export website", "start over"],
  };

  const state = {
    files: { ...starterFiles },
    activeFile: "html",
    projectId: "",
    projectName: "Untitled Project",
    projects: [],
    lastAudit: null,
    lastUrl: "",
    lastOutput: "",
    voiceActive: false,
    busy: false,
    recognition: null,
  };

  const $ = (id) => document.getElementById(id);
  const byAction = (action) => document.querySelector(`[data-action="${action}"]`);

  function announce(text) {
    const node = $("srAnnouncer");
    if (node) node.textContent = text;
  }

  function editor(file) {
    return $({ html: "htmlEditor", css: "cssEditor", js: "jsEditor" }[file]);
  }

  function currentEditor() {
    return editor(state.activeFile);
  }

  function syncFromEditors() {
    for (const file of ["html", "css", "js"]) {
      const node = editor(file);
      if (node) state.files[file] = node.value;
    }
  }

  function setFile(file, value) {
    state.files[file] = String(value || "");
    const node = editor(file);
    if (node && node.value !== state.files[file]) node.value = state.files[file];
  }

  function setFiles(files) {
    setFile("html", files.html || "");
    setFile("css", files.css || "");
    setFile("js", files.js || "");
    persistDrafts();
  }

  function persistDrafts() {
    try {
      sessionStorage.setItem("codeup_html_draft", state.files.html);
      sessionStorage.setItem("codeup_css_draft", state.files.css);
      sessionStorage.setItem("codeup_js_draft", state.files.js);
    } catch (error) {}
  }

  function loadDrafts() {
    try {
      const html = sessionStorage.getItem("codeup_html_draft");
      const css = sessionStorage.getItem("codeup_css_draft");
      const js = sessionStorage.getItem("codeup_js_draft");
      if (html) state.files.html = html;
      if (css) state.files.css = css;
      if (js) state.files.js = js;
    } catch (error) {}
  }

  function combineDocument() {
    let html = state.files.html || starterFiles.html;
    html = html.replace(/\s*<style\b[^>]*id=["']codeup-managed-css["'][^>]*>[\s\S]*?<\/style>/gi, "");
    html = html.replace(/\s*<script\b[^>]*id=["']codeup-managed-js["'][^>]*>[\s\S]*?<\/script>/gi, "");
    html = html.replace(/\s*<link\b[^>]*href=["'](?:\.\/)?style\.css["'][^>]*>/gi, "");
    html = html.replace(/\s*<script\b[^>]*src=["'](?:\.\/)?script\.js["'][^>]*>\s*<\/script>/gi, "");
    if (state.files.css.trim()) {
      const block = `\n<style id="codeup-managed-css">\n${state.files.css.trim()}\n</style>\n`;
      html = /<\/head\s*>/i.test(html) ? html.replace(/<\/head\s*>/i, `${block}</head>`) : `${block}${html}`;
    }
    if (state.files.js.trim()) {
      const block = `\n<script id="codeup-managed-js">\n${state.files.js.trim()}\n</script>\n`;
      html = /<\/body\s*>/i.test(html) ? html.replace(/<\/body\s*>/i, `${block}</body>`) : `${html}${block}`;
    }
    return html;
  }

  function sourceHtml() {
    let html = state.files.html || starterFiles.html;
    if (state.files.css.trim() && !/href=["'](?:\.\/)?style\.css["']/i.test(html)) {
      html = /<\/head\s*>/i.test(html) ? html.replace(/<\/head\s*>/i, `  <link rel="stylesheet" href="style.css">\n</head>`) : `<link rel="stylesheet" href="style.css">\n${html}`;
    }
    if (state.files.js.trim() && !/src=["'](?:\.\/)?script\.js["']/i.test(html)) {
      html = /<\/body\s*>/i.test(html) ? html.replace(/<\/body\s*>/i, `  <script src="script.js" defer></script>\n</body>`) : `${html}\n<script src="script.js" defer></script>`;
    }
    return html;
  }

  async function apiJson(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await response.json();
    if (!response.ok || data.success === false) throw new Error(data.error || `Request failed: ${response.status}`);
    return data;
  }

  function setBusy(isBusy, label) {
    state.busy = isBusy;
    const stop = $("stopBtn");
    if (stop) stop.hidden = !(isBusy || state.voiceActive);
    const status = $("voiceStatus");
    if (status) status.textContent = isBusy ? label || "Working" : state.voiceActive ? "Listening" : "Voice off";
  }

  function writeOutput(message, nextCommand = "") {
    const text = String(message || "").trim();
    state.lastOutput = nextCommand ? `${text}\n\nTry: ${nextCommand}` : text;
    const output = $("output");
    const empty = $("outputEmpty");
    const body = $("outputBody");
    const toggle = $("outputToggleBtn");
    if (empty) empty.hidden = !!state.lastOutput;
    if (output) output.textContent = state.lastOutput;
    if (body) body.hidden = false;
    if (toggle) {
      toggle.textContent = "Hide";
      toggle.setAttribute("aria-expanded", "true");
    }
    announce(text);
  }

  function showError(error) {
    writeOutput(error && error.message ? error.message : "Something went wrong.", "try again");
  }

  function switchFile(file) {
    if (!["html", "css", "js"].includes(file)) return;
    syncFromEditors();
    state.activeFile = file;
    for (const name of ["html", "css", "js"]) {
      const tab = $({ html: "tabHtml", css: "tabCss", js: "tabJs" }[name]);
      const panel = $({ html: "panelHtml", css: "panelCss", js: "panelJs" }[name]);
      if (tab) tab.setAttribute("aria-selected", name === file ? "true" : "false");
      if (panel) panel.hidden = name !== file;
    }
    const node = currentEditor();
    if (node) {
      node.value = state.files[file];
      node.focus();
    }
  }

  async function publishPreview() {
    syncFromEditors();
    const data = await apiJson("/publish-site", {
      method: "POST",
      body: JSON.stringify({ html: sourceHtml(), css: state.files.css, js: state.files.js, project_id: state.projectId, current_page: "home" }),
    });
    state.lastUrl = data.url;
    const preview = $("sitePreview");
    if (preview) {
      let frame = $("sitePreviewFrame");
      if (!frame) {
        frame = document.createElement("iframe");
        frame.id = "sitePreviewFrame";
        frame.title = "Student website preview";
        frame.setAttribute("sandbox", "allow-scripts allow-forms allow-modals");
        preview.appendChild(frame);
      }
      frame.src = `${data.url}?t=${Date.now()}`;
    }
    const open = $("sitePreviewOpenBtn");
    if (open) {
      open.disabled = false;
      open.dataset.url = data.url;
    }
    return data.url;
  }

  async function runPreview() {
    setBusy(true, "Publishing");
    try {
      await publishPreview();
      writeOutput("Preview is ready.", "check accessibility");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function generateWebsite(prompt) {
    const request = String(prompt || $("commandInput")?.value || "").trim();
    if (!request) {
      writeOutput("Describe the website you want first.", "make a website for my robotics club");
      return;
    }
    setBusy(true, "Building");
    try {
      syncFromEditors();
      const data = await apiJson("/generate-site", {
        method: "POST",
        body: JSON.stringify({ prompt: request, html: state.files.html, css: state.files.css, js: state.files.js, project_id: state.projectId }),
      });
      setFiles({ html: data.html, css: data.css, js: data.js });
      await publishPreview();
      writeOutput("Your website is ready. You can edit the files or preview it now.", "check accessibility");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function editWebsite(instruction) {
    const request = String(instruction || "").trim();
    if (!request) return generateWebsite(request);
    setBusy(true, "Editing");
    try {
      syncFromEditors();
      const data = await apiJson("/edit-site", {
        method: "POST",
        body: JSON.stringify({ instruction: request, html: state.files.html, css: state.files.css, js: state.files.js, project_id: state.projectId }),
      });
      setFiles({ html: data.html, css: data.css, js: data.js });
      await publishPreview();
      writeOutput("Updated the website and refreshed the preview.", "run website");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function checkAccessibility() {
    setBusy(true, "Checking");
    try {
      syncFromEditors();
      const data = await apiJson("/html-audit", { method: "POST", body: JSON.stringify({ html: combineDocument(), project_id: state.projectId }) });
      state.lastAudit = data.audit;
      const issues = (data.audit.issues || []).slice(0, 5).map((item) => `${item.severity}: ${item.description}`).join("\n");
      writeOutput(`Accessibility score: ${data.audit.score}/100\n${issues || "No major issues found."}`, "fix accessibility issues");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function fixAccessibility() {
    setBusy(true, "Fixing");
    try {
      syncFromEditors();
      const data = await apiJson("/audit-autofix", { method: "POST", body: JSON.stringify({ html: combineDocument(), fix_all: true, project_id: state.projectId }) });
      const fixed = splitDocument(data.code || data.fixed_html || state.files.html);
      setFiles(fixed);
      await publishPreview();
      writeOutput("Applied safe accessibility fixes and refreshed the preview.", "is this ready to share");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function runLearning(path, payload, label, nextCommand) {
    setBusy(true, "Checking");
    try {
      syncFromEditors();
      const data = await apiJson(path, { method: "POST", body: JSON.stringify({ html: state.files.html, css: state.files.css, js: state.files.js, ...payload }) });
      writeOutput(data.text || data.message || data.summary || data.answer || data.run_summary || data.debug_report || data.readiness_score || data.description || data.code_map || data.version_history || label, nextCommand);
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function startTutorial() {
    setBusy(true, "Loading tutorial");
    try {
      const data = await apiJson("/guided-build/steps");
      const steps = (data.steps || []).map((step, index) => `${index + 1}. ${step.title || step.name || step.id}`).join("\n");
      writeOutput(steps || "Tutorial ready.", "make a website for my robotics club");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function explainFile(file) {
    const endpoint = "/project-file-explanation";
    await runLearning(endpoint, { file }, `Explained ${file}.`, "describe preview");
  }

  async function saveProject() {
    syncFromEditors();
    const nameInput = $("projectNameInput");
    state.projectName = (nameInput && nameInput.value.trim()) || state.projectName || "Untitled Project";
    setBusy(true, "Saving");
    try {
      const combined = combineDocument();
      const payload = { name: state.projectName, html: combined, pages: { home: combined }, current_page: "home" };
      let data;
      if (state.projectId) {
        data = await apiJson(`/projects/${state.projectId}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        data = await apiJson("/projects", { method: "POST", body: JSON.stringify(payload) });
      }
      state.projectId = data.project.id;
      state.projectName = data.project.name;
      await refreshProjects();
      writeOutput(`Saved ${state.projectName}.`, "export website");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  async function refreshProjects() {
    try {
      const data = await apiJson("/projects");
      state.projects = data.projects || [];
      const select = $("projectSelect");
      if (select) {
        select.innerHTML = "";
        for (const project of state.projects) {
          const option = document.createElement("option");
          option.value = project.id;
          option.textContent = project.name || "Untitled Project";
          select.appendChild(option);
        }
      }
    } catch (error) {}
  }

  async function openProject() {
    const select = $("projectSelect");
    const id = select && select.value ? select.value : state.projects[0]?.id;
    if (!id) {
      writeOutput("No saved projects found.", "save project");
      return;
    }
    setBusy(true, "Opening");
    try {
      const data = await apiJson(`/projects/${id}`);
      const project = data.project;
      state.projectId = project.id;
      state.projectName = project.name || "Untitled Project";
      const page = project.pages?.[project.current_page] || project.pages?.home || project.html || starterFiles.html;
      const split = splitDocument(page);
      setFiles(split);
      const nameInput = $("projectNameInput");
      if (nameInput) nameInput.value = state.projectName;
      await publishPreview();
      writeOutput(`Opened ${state.projectName}.`, "run website");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  function splitDocument(documentText) {
    let html = String(documentText || "");
    let css = "";
    let js = "";
    html = html.replace(/<style\b[^>]*>([\s\S]*?)<\/style>/gi, (match, content) => {
      css += `${content.trim()}\n`;
      return "";
    });
    html = html.replace(/<script\b(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi, (match, content) => {
      js += `${content.trim()}\n`;
      return "";
    });
    return { html: html.trim() || starterFiles.html, css: css.trim(), js: js.trim() };
  }

  async function exportZip() {
    syncFromEditors();
    setBusy(true, "Exporting");
    try {
      const response = await fetch("/export-site.zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: state.projectId,
          name: state.projectName,
          files: { "index.html": sourceHtml(), "style.css": state.files.css, "script.js": state.files.js },
          audit: state.lastAudit,
          project_type: "website",
        }),
      });
      if (!response.ok) throw new Error("Could not export ZIP.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(state.projectName || "codeup-site").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "codeup-site"}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      writeOutput("Exported the website ZIP.", "open preview");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  function newProject() {
    state.projectId = "";
    state.projectName = "Untitled Project";
    setFiles(starterFiles);
    const nameInput = $("projectNameInput");
    if (nameInput) nameInput.value = state.projectName;
    writeOutput("Started a new website.", "make a website for my robotics club");
    runPreview();
  }

  async function resetWorkspace() {
    try {
      await apiJson("/reset-session", { method: "POST", body: JSON.stringify({}) });
    } catch (error) {}
    newProject();
  }

  function openOverlay(name) {
    closeOverlays();
    const overlay = $(`${name}Overlay`);
    const panel = $(`${name}Panel`) || $(`${name}Menu`);
    if (overlay) overlay.hidden = false;
    if (panel) panel.focus();
    const btn = $(`${name}Btn`);
    if (btn) btn.setAttribute("aria-expanded", "true");
  }

  function closeOverlays() {
    for (const id of ["moreOverlay", "settingsOverlay", "helpOverlay", "projectOverlay"]) {
      const overlay = $(id);
      if (overlay) overlay.hidden = true;
    }
    for (const id of ["moreBtn", "settingsBtn", "helpBtn"]) {
      const btn = $(id);
      if (btn) btn.setAttribute("aria-expanded", "false");
    }
  }

  function renderHelp(filter = "") {
    const root = $("helpCommandList");
    if (!root) return;
    const q = filter.trim().toLowerCase();
    root.innerHTML = "";
    for (const [group, commands] of Object.entries(helpGroups)) {
      const visible = commands.filter((cmd) => !q || cmd.toLowerCase().includes(q) || group.toLowerCase().includes(q));
      if (!visible.length) continue;
      const section = document.createElement("section");
      section.className = "ide-help-group";
      const title = document.createElement("h2");
      title.textContent = group;
      section.appendChild(title);
      for (const cmd of visible) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "ide-chip";
        button.textContent = cmd;
        button.addEventListener("click", () => {
          closeOverlays();
          const input = $("commandInput");
          if (input) input.value = cmd;
          runCommand(cmd);
        });
        section.appendChild(button);
      }
      root.appendChild(section);
    }
  }

  function loadSettings() {
    let settings = {};
    try {
      settings = JSON.parse(localStorage.getItem("codeup_settings") || "{}");
    } catch (error) {}
    for (const id of ["colorVisionMode", "languageSelector"]) {
      const node = $(id);
      if (node && settings[id]) node.value = settings[id];
    }
    for (const id of ["dyslexiaToggle", "motionToggle", "nightToggle", "demoModeBtn"]) {
      const node = $(id);
      if (node) node.checked = !!settings[id];
    }
    applySettings();
  }

  function saveSettings() {
    const settings = {};
    for (const id of ["colorVisionMode", "languageSelector"]) settings[id] = $(id)?.value || "";
    for (const id of ["dyslexiaToggle", "motionToggle", "nightToggle", "demoModeBtn"]) settings[id] = !!$(id)?.checked;
    localStorage.setItem("codeup_settings", JSON.stringify(settings));
    applySettings();
  }

  function applySettings() {
    document.body.dataset.colorVision = $("colorVisionMode")?.value || "default";
    document.body.classList.toggle("dyslexia-mode", !!$("dyslexiaToggle")?.checked);
    document.body.classList.toggle("reduced-motion", !!$("motionToggle")?.checked);
    document.body.classList.toggle("night-mode", !!$("nightToggle")?.checked);
    document.body.classList.toggle("demo-mode", !!$("demoModeBtn")?.checked);
  }

  function moreAction(action) {
    closeOverlays();
    const map = {
      "new-project": newProject,
      "open-project": () => { openOverlay("project"); refreshProjects(); },
      "save-project": saveProject,
      "export-zip": exportZip,
      "run-website": () => runLearning("/website-runtime-teacher", {}, "Website runtime checked.", "debug website"),
      "describe-preview": () => runLearning("/preview-description", {}, "Preview described.", "code map"),
      "code-map": () => runLearning("/code-map", { query: "" }, "Code map ready.", "explain CSS"),
      "check-accessibility": checkAccessibility,
      "fix-accessibility": fixAccessibility,
      "version-history": () => runLearning("/version-history", { versions: [] }, "Version history ready.", "save project"),
      "start-tutorial": () => runCommand("start tutorial"),
      "reset-workspace": resetWorkspace,
    };
    const fn = map[action];
    if (fn) fn();
  }

  function isBuildCommand(command) {
    return /\b(make|build|create|generate)\b/i.test(command) && /\b(site|website|webpage|app|quiz|portfolio|club|page)\b/i.test(command);
  }

  function isEditCommand(command) {
    return /\b(add|change|make it|remove|update|simpler|professional|contact|title|section|color|colour)\b/i.test(command) && !isBuildCommand(command);
  }

  function helpAlias(command) {
    return /^(help|what can i do here|list of commands|show commands|commands)$/i.test(command.trim());
  }

  async function runCommand(raw) {
    const command = String(raw || $("commandInput")?.value || "").trim();
    if (!command) return;
    if ($("commandInput")) $("commandInput").value = "";
    if (helpAlias(command)) {
      renderHelp();
      openOverlay("help");
      writeOutput("Help is open. Choose a command or search the list.", "make a website for my robotics club");
      return;
    }
    if (/^(stop|stop everything|cancel)$/i.test(command)) {
      stopActivity();
      writeOutput("Stopped.", "describe a website");
      return;
    }
    if (/^open preview$/i.test(command)) return openPreview();
    if (/^save project$/i.test(command)) return saveProject();
    if (/^(open project|projects)$/i.test(command)) { openOverlay("project"); return refreshProjects(); }
    if (/^(export|export website|export zip)$/i.test(command)) return exportZip();
    if (/^(start over|reset workspace|new project)$/i.test(command)) return resetWorkspace();
    if (/^(check accessibility|audit|accessibility audit)$/i.test(command)) return checkAccessibility();
    if (/^(fix accessibility|fix accessibility issues|apply safe fixes)$/i.test(command)) return fixAccessibility();
    if (/^run website$/i.test(command)) return runLearning("/website-runtime-teacher", {}, "Website runtime checked.", "debug website");
    if (/^debug website|debug this website$/i.test(command)) return runLearning("/website-debug-teacher", {}, "Debug report ready.", "is this ready to share");
    if (/^is this ready to share|readiness$/i.test(command)) return runLearning("/accessibility-readiness-score", {}, "Readiness checked.", "export website");
    if (/^code map$/i.test(command)) return runLearning("/code-map", { query: "" }, "Code map ready.", "explain CSS");
    if (/^describe preview$/i.test(command)) return runLearning("/preview-description", {}, "Preview described.", "check accessibility");
    if (/^what changed$/i.test(command)) return runLearning("/mistake-replay", { html_before: "", html_after: state.files.html, css_before: "", css_after: state.files.css, js_before: "", js_after: state.files.js }, "Change summary ready.", "run website");
    if (/^explain html$/i.test(command)) return explainFile("html");
    if (/^explain css$/i.test(command)) return explainFile("css");
    if (/^explain javascript|explain js$/i.test(command)) return explainFile("script.js");
    if (/^start tutorial$/i.test(command)) return startTutorial();
    if (isBuildCommand(command)) return generateWebsite(command);
    if (isEditCommand(command)) return editWebsite(command);
    return runChat(command);
  }

  async function runChat(message) {
    setBusy(true, "Thinking");
    try {
      syncFromEditors();
      const data = await apiJson("/html-chat", { method: "POST", body: JSON.stringify({ message, html: combineDocument(), language: $("languageSelector")?.value || "en" }) });
      writeOutput(data.reply || "Done.", "make a website for my robotics club");
    } catch (error) {
      showError(error);
    } finally {
      setBusy(false);
    }
  }

  function openPreview() {
    if (state.lastUrl) window.open(state.lastUrl, "_blank", "noopener");
  }

  function stopActivity() {
    if (state.recognition) {
      try { state.recognition.stop(); } catch (error) {}
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    state.voiceActive = false;
    setBusy(false);
  }

  function toggleVoice() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      writeOutput("Voice input is not available in this browser. Type commands instead.", "make a website for my robotics club");
      return;
    }
    if (state.voiceActive) {
      stopActivity();
      return;
    }
    state.recognition = new SpeechRecognition();
    state.recognition.lang = $("languageSelector")?.value === "hi" ? "hi-IN" : "en-US";
    state.recognition.interimResults = false;
    state.recognition.onstart = () => {
      state.voiceActive = true;
      setBusy(false);
      const button = $("voiceButton");
      if (button) button.setAttribute("aria-pressed", "true");
    };
    state.recognition.onend = () => {
      state.voiceActive = false;
      setBusy(false);
      const button = $("voiceButton");
      if (button) button.setAttribute("aria-pressed", "false");
    };
    state.recognition.onresult = (event) => {
      const transcript = event.results?.[0]?.[0]?.transcript || "";
      runCommand(transcript);
    };
    state.recognition.start();
  }

  function bindEvents() {
    for (const file of ["html", "css", "js"]) {
      const node = editor(file);
      if (node) {
        node.value = state.files[file];
        node.addEventListener("input", () => {
          state.files[file] = node.value;
          persistDrafts();
        });
      }
    }
    for (const tab of document.querySelectorAll(".ide-tab[data-file]")) tab.addEventListener("click", () => switchFile(tab.dataset.file));
    $("sendCommandBtn")?.addEventListener("click", () => runCommand());
    $("runBtn")?.addEventListener("click", runPreview);
    $("previewReloadBtn")?.addEventListener("click", runPreview);
    $("voiceButton")?.addEventListener("click", toggleVoice);
    $("stopBtn")?.addEventListener("click", stopActivity);
    $("moreBtn")?.addEventListener("click", () => openOverlay("more"));
    $("settingsBtn")?.addEventListener("click", () => openOverlay("settings"));
    $("helpBtn")?.addEventListener("click", () => { renderHelp(); openOverlay("help"); });
    $("closeSettingsBtn")?.addEventListener("click", closeOverlays);
    $("closeHelpBtn")?.addEventListener("click", closeOverlays);
    $("closeProjectBtn")?.addEventListener("click", closeOverlays);
    $("projectOpenBtn")?.addEventListener("click", openProject);
    $("projectNewBtn")?.addEventListener("click", newProject);
    $("sitePreviewOpenBtn")?.addEventListener("click", openPreview);
    $("outputToggleBtn")?.addEventListener("click", () => {
      const body = $("outputBody");
      const button = $("outputToggleBtn");
      if (!body || !button) return;
      body.hidden = !body.hidden;
      button.textContent = body.hidden ? "Show" : "Hide";
      button.setAttribute("aria-expanded", body.hidden ? "false" : "true");
    });
    for (const button of document.querySelectorAll("#moreMenu [data-action]")) button.addEventListener("click", () => moreAction(button.dataset.action));
    for (const id of ["colorVisionMode", "languageSelector", "dyslexiaToggle", "motionToggle", "nightToggle", "demoModeBtn"]) $(id)?.addEventListener("change", saveSettings);
    $("helpSearch")?.addEventListener("input", (event) => renderHelp(event.target.value));
    $("commandInput")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") runCommand();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (!$('moreOverlay')?.hidden || !$('settingsOverlay')?.hidden || !$('helpOverlay')?.hidden || !$('projectOverlay')?.hidden) closeOverlays();
        else stopActivity();
      }
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") runPreview();
    });
    $("previewDesktopBtn")?.addEventListener("click", () => setPreviewSize("desktop"));
    $("previewTabletBtn")?.addEventListener("click", () => setPreviewSize("tablet"));
    $("previewMobileBtn")?.addEventListener("click", () => setPreviewSize("mobile"));
  }

  function setPreviewSize(size) {
    const preview = $("sitePreview");
    if (preview) preview.dataset.size = size;
    for (const [id, value] of [["previewDesktopBtn", "desktop"], ["previewTabletBtn", "tablet"], ["previewMobileBtn", "mobile"]]) {
      $(id)?.setAttribute("aria-pressed", value === size ? "true" : "false");
    }
  }

  function init() {
    loadDrafts();
    bindEvents();
    loadSettings();
    renderHelp();
    refreshProjects();
    setFiles(state.files);
    switchFile("html");
    writeOutput("Ready. Describe a website to begin.", "make a website for my school robotics club");
    setTimeout(() => runPreview(), 0);
    document.body.setAttribute("data-html-mode-ready", "true");
    window.CodeUpIDE = {
      state,
      setFiles,
      switchFile,
      runCommand,
      publishPreview,
      combineDocument,
      sourceHtml,
      getHtml: () => state.files.html,
      getCss: () => state.files.css,
      getJs: () => state.files.js,
    };
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
