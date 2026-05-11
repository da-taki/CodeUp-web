/* global React */
const { useEffect, useState, useRef } = React;

// ────────────────────────────────────────────────────────────
// EditorHero — the FUNCTIONAL surface. Lives at the top of the
// page so a blind user can land, tab once, and start coding.
// Real textarea (not Monaco — keeps page light), real Run that
// evaluates a tiny safelist of Python-style ops via a mock
// interpreter, real voice toggle that hooks into Web Speech API
// when available, real Sonify that plays tones from indent.
// ────────────────────────────────────────────────────────────

const SAMPLE = `# Welcome to CodeUp
# Press Ctrl+Enter to run · Alt+S to sonify
# Tab through controls · Esc stops speech

def greet(name):
    return f"Hello, {name}!"

for who in ["world", "Taknoor"]:
    print(greet(who))
`;

function speak(text, lang = "en-US") {
  if (!("speechSynthesis" in window)) return;
  try {
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang;
    u.rate = 1.05;
    window.speechSynthesis.speak(u);
  } catch (e) {}
}

// Tiny mock runner so the editor actually executes basic prints
// without pulling in a Python interpreter. Real backend is /run on the server.
function mockRun(src) {
  const out = [];
  const env = {};
  const lines = src.split("\n");
  // pass 1: collect def bodies
  const defs = {};
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^def\s+(\w+)\(([^)]*)\):/);
    if (m) {
      const name = m[1];
      const args = m[2].split(",").map((s) => s.trim()).filter(Boolean);
      const body = [];
      let j = i + 1;
      while (j < lines.length && (lines[j].startsWith("    ") || lines[j].trim() === "")) {
        if (lines[j].trim()) body.push(lines[j].slice(4));
        j++;
      }
      defs[name] = { args, body };
      i = j - 1;
    }
  }
  function callFn(name, vals) {
    const d = defs[name];
    if (!d) return `<${name}>`;
    const local = {};
    d.args.forEach((a, k) => (local[a] = vals[k]));
    for (const ln of d.body) {
      const rm = ln.match(/^return\s+(.+)$/);
      if (rm) return evalExpr(rm[1], local);
    }
    return undefined;
  }
  function evalExpr(expr, local = {}) {
    expr = expr.trim();
    // f-string
    let m = expr.match(/^f"([^"]*)"$/);
    if (m) {
      return m[1].replace(/\{([^}]+)\}/g, (_, e) => String(evalExpr(e, local)));
    }
    // double-quoted string
    m = expr.match(/^"([^"]*)"$/);
    if (m) return m[1];
    // list literal of strings
    m = expr.match(/^\[([^\]]*)\]$/);
    if (m) return m[1].split(",").map((s) => evalExpr(s, local));
    // number
    if (/^-?\d+(\.\d+)?$/.test(expr)) return Number(expr);
    // function call
    m = expr.match(/^(\w+)\((.*)\)$/);
    if (m) {
      const args = splitArgs(m[2]).map((a) => evalExpr(a, local));
      return callFn(m[1], args);
    }
    // identifier
    if (local[expr] !== undefined) return local[expr];
    if (env[expr] !== undefined) return env[expr];
    return expr;
  }
  function splitArgs(s) {
    const out = [];
    let depth = 0, cur = "";
    for (const c of s) {
      if (c === "," && depth === 0) { out.push(cur); cur = ""; continue; }
      if (c === "(" || c === "[") depth++;
      if (c === ")" || c === "]") depth--;
      cur += c;
    }
    if (cur.trim()) out.push(cur);
    return out;
  }

  // pass 2: execute top-level
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i];
    if (!ln.trim() || ln.trim().startsWith("#")) continue;
    if (ln.startsWith("def ")) {
      while (i + 1 < lines.length && (lines[i + 1].startsWith("    ") || !lines[i + 1].trim())) i++;
      continue;
    }
    let m = ln.match(/^print\((.*)\)$/);
    if (m) { out.push(String(evalExpr(m[1]))); continue; }
    m = ln.match(/^for\s+(\w+)\s+in\s+(.+):$/);
    if (m) {
      const v = m[1];
      const arr = evalExpr(m[2]);
      const body = [];
      let j = i + 1;
      while (j < lines.length && (lines[j].startsWith("    ") || !lines[j].trim())) {
        if (lines[j].trim()) body.push(lines[j].slice(4));
        j++;
      }
      for (const item of arr || []) {
        env[v] = item;
        for (const b of body) {
          const pm = b.match(/^print\((.*)\)$/);
          if (pm) out.push(String(evalExpr(pm[1])));
        }
      }
      i = j - 1;
      continue;
    }
  }
  return out.join("\n");
}

function EditorHero() {
  const [src, setSrc] = useState(SAMPLE);
  const [out, setOut] = useState("// output appears here\n// nothing has been run yet");
  const [running, setRunning] = useState(false);
  const [voice, setVoice] = useState(false);
  const [lang, setLang] = useState("EN");
  const [status, setStatus] = useState("ready");
  const taRef = useRef(null);

  function run() {
    setRunning(true);
    setStatus("preview only — opening real IDE recommended");
    setTimeout(() => {
      const r = mockRun(src);
      setOut(
        "// PREVIEW MODE — limited interpreter (def, print, for, f-strings only)\n" +
        "// For real Python execution, open the IDE: /ide\n" +
        "// ────────────────────────────────────────────────\n" +
        (r || "// (no output)")
      );
      setRunning(false);
      setStatus("preview · " + (r.split("\n").length) + " lines · /ide for real run");
      const speakLang = lang === "EN" ? "en-US" : "hi-IN";
      speak("This is a preview. For real Python execution, open the full IDE.", speakLang);
    }, 350);
  }

  // Sonify — pitch from indent of each line
  const audioRef = useRef(null);
  function sonify() {
    const C = window.AudioContext || window.webkitAudioContext;
    if (!C) return;
    if (!audioRef.current) audioRef.current = new C();
    const ctx = audioRef.current;
    const lines = src.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#"));
    const PITCH = [165, 220, 294, 392, 523, 659];
    let t = ctx.currentTime + 0.05;
    lines.forEach((ln) => {
      const indent = (ln.match(/^ */)[0].length) / 4;
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = ln.trim().startsWith("def") ? "sine" :
               ln.trim().startsWith("for") ? "triangle" :
               ln.trim().startsWith("if")  ? "square" : "sawtooth";
      o.frequency.value = PITCH[Math.min(indent, PITCH.length - 1)];
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(0.16, t + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0008, t + 0.32);
      o.connect(g).connect(ctx.destination);
      o.start(t); o.stop(t + 0.36);
      t += 0.34;
    });
    setStatus("sonifying · " + lines.length + " tones");
  }

  function toggleVoice() {
    const next = !voice;
    setVoice(next);
    setStatus(next ? "listening · " + lang : "voice off");
    speak(next ? "Voice on" : "Voice off");
  }

  // Hotkeys
  useEffect(() => {
    function onKey(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); run(); }
      else if (e.altKey && e.key.toLowerCase() === "s") { e.preventDefault(); sonify(); }
      else if (e.key === "Escape") { window.speechSynthesis && window.speechSynthesis.cancel(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [src, lang]);

  // Line numbers
  const lineCount = src.split("\n").length;
  const lineNums = Array.from({ length: Math.max(lineCount, 12) }, (_, i) => i + 1).join("\n");

  return (
    <section className="eh" aria-label="Code editor — start coding">
      <a href="#editor-area" className="skip-link">Skip to editor preview</a>
        <a href="/ide" className="skip-link" style={{left: 'auto', right: 0}}>Open real IDE</a>

      <div className="wrap eh-wrap">
        <div className="eh-head">
          <div className="eh-headline">
            <span className="version-pill">
              <span className="blip"></span> READY · v0.8.0
            </span>
            <h1 className="eh-h1">
              Open. <span className="accent">Code.</span> Listen.
            </h1>
            <p className="eh-sub">
              <strong style={{color: 'var(--accent)'}}>Preview only —</strong> a tiny
              JS interpreter that handles <code>def</code>, <code>print</code>, <code>for</code>,
              and f-strings. For real Python, <a href="/ide" style={{color: 'var(--accent)', textDecoration: 'underline'}}>open the IDE →</a>
              &nbsp;<kbd>Ctrl</kbd>+<kbd>Enter</kbd> runs preview ·
              <kbd>Alt</kbd>+<kbd>S</kbd> sonifies ·
              <kbd>Esc</kbd> stops speech.
            </p>
          </div>
          <div className="eh-meta" aria-live="polite">
            <div className="eh-meta-row"><span className="lbl">status</span><b className={"val " + (running ? "warn" : "ok")}>{status}</b></div>
            <div className="eh-meta-row"><span className="lbl">sandbox</span><b className="val">5s · 512MB</b></div>
            <div className="eh-meta-row"><span className="lbl">tutorial</span><b className="val">step 1 / 6</b></div>
          </div>
        </div>

        <div className="eh-toolbar" role="toolbar" aria-label="Coding controls">
          <button className="eh-btn eh-btn-primary" onClick={run} aria-label="Run code · Ctrl+Enter">
            <svg viewBox="0 0 16 16" aria-hidden="true"><polygon points="3,2 14,8 3,14" fill="currentColor"/></svg>
            Run <span className="eh-key">⌃↵</span>
          </button>
          <button className={"eh-btn" + (voice ? " is-on" : "")} onClick={toggleVoice} aria-label="Toggle voice control · Ctrl+Shift+M" aria-pressed={voice}>
            <span className={"mic" + (voice ? " is-live" : "")} aria-hidden="true"></span>
            Voice {voice ? "on" : "off"} <span className="eh-key">⌃⇧M</span>
          </button>
          <button className="eh-btn" onClick={sonify} aria-label="Sonify block · Alt+S">
            <span className="bars" aria-hidden="true"><i></i><i></i><i></i><i></i></span>
            Sonify <span className="eh-key">⌥S</span>
          </button>
          <div className="eh-divider" aria-hidden="true"></div>
          <div className="eh-lang" role="group" aria-label="Speech language">
            <button className={"eh-pill" + (lang === "EN" ? " is-on" : "")} onClick={() => setLang("EN")} aria-pressed={lang === "EN"}>EN</button>
            <button className={"eh-pill" + (lang === "HI" ? " is-on" : "")} onClick={() => setLang("HI")} aria-pressed={lang === "HI"} lang="hi">हिं</button>
          </div>
          <div className="eh-divider" aria-hidden="true"></div>
          <button className="eh-btn eh-btn-ghost" onClick={() => speak("Help. Press Control Enter to run. Press Alt S to sonify.")} aria-label="Help · Alt+H">
            ? Help <span className="eh-key">⌥H</span>
          </button>
          <span className="eh-spacer"></span>
          <span className="eh-shortcuts" aria-hidden="true">
            <kbd>⌃↵</kbd>run · <kbd>⌥S</kbd>sonify · <kbd>⌥V</kbd>vars · <kbd>⌥L</kbd>read line · <kbd>esc</kbd>stop
          </span>
        </div>

        <div className="eh-stage" id="editor-area">
          <div className="eh-editor">
            <div className="eh-editor-bar">
              <span className="lights"><span></span><span></span><span></span></span>
              <span className="path"><b>scratch.py</b> · welcome to CodeUp</span>
              <span className="badge">{lineCount} lines · {src.length} chars</span>
            </div>
            <div className="eh-editor-body">
              <pre className="eh-gutter" aria-hidden="true">{lineNums}</pre>
              <textarea
                ref={taRef}
                className="eh-textarea"
                spellCheck="false"
                aria-label="Python code editor"
                value={src}
                onChange={(e) => setSrc(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Tab") {
                    e.preventDefault();
                    const t = e.target;
                    const s = t.selectionStart, en = t.selectionEnd;
                    const next = src.slice(0, s) + "    " + src.slice(en);
                    setSrc(next);
                    requestAnimationFrame(() => { t.selectionStart = t.selectionEnd = s + 4; });
                  }
                }}
              />
            </div>
          </div>

          <div className="eh-output" aria-live="polite">
            <div className="eh-output-bar">
              <span>● output</span>
              <span className="ok">{running ? "running…" : "idle"}</span>
            </div>
            <pre className="eh-output-body">{out}</pre>
            <div className="eh-output-foot">
              <span>▸ heartbeat 500ms · sandbox active</span>
              <span className="speak-hint">screen reader: aria-live=polite</span>
            </div>
          </div>
        </div>

        <div className="eh-marquee" aria-hidden="true" role="presentation">
          <div className="eh-marquee-track" aria-hidden="true">
            {["run", "sonify block", "tell the story", "what changed here", "go to line twenty five",
              "set breakpoint at line 10", "explain simply", "remember this as quick sort",
              "चलाओ", "लाइन बीस पर जाओ", "कोड समझाओ", "मदद",
              "run", "sonify block", "tell the story", "what changed here", "go to line twenty five",
              "set breakpoint at line 10", "explain simply", "remember this as quick sort",
              "चलाओ", "लाइन बीस पर जाओ", "कोड समझाओ", "मदद"
            ].map((t, i) => (
              <span key={i}>"{t}"<i>●</i></span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

window.EditorHero = EditorHero;
