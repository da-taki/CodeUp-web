/* global React */
const { useEffect, useState, useRef } = React;

// ────────────────────────────────────────────────────────────
// Voice typewriter — cycles through bilingual command list
// ────────────────────────────────────────────────────────────
const VOICE_LINES = [
  { say: "run the code",                     act: "▸ python sieve.py", lang: "EN", key: "Ctrl+Enter" },
  { say: "go to line twenty five",           act: "▸ cursor → line 25", lang: "EN", key: "Alt+G" },
  { say: "sonify this block",                act: "▸ playing 9 tones", lang: "EN", key: "Alt+S" },
  { say: "what changed here",                act: "▸ x: 0 → 10, y added", lang: "EN", key: "—" },
  { say: "tell the story",                   act: "▸ narrating trace", lang: "EN", key: "—" },
  { say: "set breakpoint at line 10",        act: "▸ bp added · line 10", lang: "EN", key: "F9" },
  { say: "explain simply",                   act: "▸ beginner-mode error", lang: "EN", key: "—" },
  { say: "remember this as quick sort",      act: "▸ macro saved", lang: "EN", key: "—" },
  { say: "चलाओ",                              act: "▸ कोड चल रहा है",  lang: "हिं", key: "Ctrl+Enter" },
  { say: "लाइन बीस पर जाओ",                  act: "▸ cursor → line 20", lang: "हिं", key: "Alt+G" },
  { say: "कोड समझाओ",                         act: "▸ AI summary",       lang: "हिं", key: "—" },
  { say: "मदद",                               act: "▸ help opened",      lang: "हिं", key: "Alt+H" },
];

function Voice() {
  const [idx, setIdx] = useState(0);
  const [typed, setTyped] = useState("");

  useEffect(() => {
    const target = VOICE_LINES[idx].say;
    let i = 0;
    setTyped("");
    const noMo = document.body.classList.contains("no-motion");
    if (noMo) { setTyped(target); return; }
    const t = setInterval(() => {
      i++;
      setTyped(target.slice(0, i));
      if (i >= target.length) clearInterval(t);
    }, 55);
    const next = setTimeout(() => setIdx((v) => (v + 1) % VOICE_LINES.length), 3600);
    return () => { clearInterval(t); clearTimeout(next); };
  }, [idx]);

  const cur = VOICE_LINES[idx];

  return (
    <section id="speak" className="voice">
      <div className="wrap">
        <div className="reveal section-head">
          <div>
            <div className="eyebrow" style={{ marginBottom: 16 }}>02 — Voice</div>
            <h2>Just <span className="accent">say it.</span></h2>
          </div>
          <p className="desc">
            A grammar-based intent parser. Not exact-match. Speak naturally in
            English or Hindi — say what you'd say to a person who can read code
            for you. CodeUp will figure it out.
          </p>
        </div>

        <div className="reveal voice-card">
          <div className="voice-mic">
            <div className="voice-mic-status">
              <span className="live"></span> LISTENING · {cur.lang}
            </div>
            <div className="voice-quote">
              "{typed}<span className="cursor"></span>"
            </div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--accent-deep)" }}>
              {cur.act}
            </div>
            <div className="voice-meta">
              <div><div className="label">Language</div><div className="value">{cur.lang === "EN" ? "English (en-US)" : "हिंदी (hi-IN)"}</div></div>
              <div><div className="label">Hotkey</div><div className="value">{cur.key}</div></div>
              <div><div className="label">Engine</div><div className="value">Web Speech API</div></div>
            </div>
            <div className="voice-mic-wave" aria-hidden="true"></div>
          </div>

          <div className="voice-list">
            <div className="voice-list-head">
              <span>command palette</span>
              <span>{idx + 1}/{VOICE_LINES.length}</span>
            </div>
            {VOICE_LINES.map((c, i) => (
              <div key={i} className={"voice-cmd" + (i === idx ? " is-active" : "")}>
                <span className="num">{String(i + 1).padStart(2, "0")}</span>
                <span>"{c.say}"</span>
                <span className="key">{c.lang}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

// ────────────────────────────────────────────────────────────
// IDE preview — animated trace stepper
// ────────────────────────────────────────────────────────────
const IDE_LINES = [
  { n: 1, html: '<span class="tk-cmt"># sieve of eratosthenes</span>' },
  { n: 2, html: '<span class="tk-kw">def</span> <span class="tk-fn">primes_up_to</span>(<span class="tk-op">n</span>):' },
  { n: 3, html: '\u00A0\u00A0sieve = [<span class="tk-kw">True</span>] * (n + <span class="tk-num">1</span>)' },
  { n: 4, html: '\u00A0\u00A0sieve[<span class="tk-num">0</span>] = sieve[<span class="tk-num">1</span>] = <span class="tk-kw">False</span>' },
  { n: 5, html: '\u00A0\u00A0<span class="tk-kw">for</span> i <span class="tk-kw">in</span> <span class="tk-fn">range</span>(<span class="tk-num">2</span>, <span class="tk-fn">int</span>(n**<span class="tk-num">0.5</span>)+<span class="tk-num">1</span>):', bp: true },
  { n: 6, html: '\u00A0\u00A0\u00A0\u00A0<span class="tk-kw">if</span> sieve[i]:' },
  { n: 7, html: '\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0<span class="tk-kw">for</span> j <span class="tk-kw">in</span> <span class="tk-fn">range</span>(i*i, n+<span class="tk-num">1</span>, i):' },
  { n: 8, html: '\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0\u00A0sieve[j] = <span class="tk-kw">False</span>' },
  { n: 9, html: '\u00A0\u00A0<span class="tk-kw">return</span> [i <span class="tk-kw">for</span> i, p <span class="tk-kw">in</span> <span class="tk-fn">enumerate</span>(sieve) <span class="tk-kw">if</span> p]' },
  { n: 10, html: '' },
  { n: 11, html: '<span class="tk-fn">print</span>(<span class="tk-fn">primes_up_to</span>(<span class="tk-num">30</span>))' },
];

const TRACE = [
  { line: 2, label: "enter primes_up_to(n=30)", delta: "n = 30" },
  { line: 3, label: "build sieve", delta: "sieve = [T]·31" },
  { line: 5, label: "loop range 2..6", delta: "i = 2" },
  { line: 7, label: "inner loop · i*i = 4", delta: "j = 4, 6, 8, …" },
  { line: 5, label: "next outer step", delta: "i = 3" },
  { line: 7, label: "mark composites of 3", delta: "j = 9, 12, 15, …" },
  { line: 9, label: "comprehension returns 10 primes", delta: "[2, 3, 5, 7, 11, 13, …]" },
];

function IDE() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (document.body.classList.contains("no-motion")) return;
    const id = setInterval(() => setStep((s) => (s + 1) % TRACE.length), 1900);
    return () => clearInterval(id);
  }, []);

  const cur = TRACE[step];

  return (
    <section id="ide" className="ide-section">
      <div className="wrap">
        <div className="reveal section-head">
          <div>
            <div className="eyebrow" style={{ marginBottom: 16 }}>03 — Trace mode</div>
            <h2>
              Step through. <span className="accent">Hear the story.</span>
            </h2>
          </div>
          <p className="desc">
            5,000 events captured per run. Step forward, step back, ask "what
            changed here," or say "tell the story" and CodeUp narrates the trace
            as a sequence of plain-English sentences — variables, branches, and all.
          </p>
        </div>

        <div className="reveal ide">
          <div className="ide-bar">
            <div className="lights"><span></span><span></span><span></span></div>
            <span className="path"><b>sieve.py</b> &nbsp;·&nbsp; ~/codeup/snippets</span>
            <div className="right">
              <span className="key">⌃↵ run</span>
              <span className="key">alt+N step</span>
              <span className="key">esc stop</span>
            </div>
          </div>

          <div className="ide-body">
            <aside className="ide-side">
              <h4>Snippets</h4>
              <div className="ide-snippet is-current">
                <span>sieve.py</span>
                <span className="badge">11L</span>
              </div>
              <div className="ide-snippet"><span>fibonacci.py</span><span className="badge">8L</span></div>
              <div className="ide-snippet"><span>palindrome.py</span><span className="badge">6L</span></div>
              <div className="ide-snippet"><span>quick_sort.py</span><span className="badge">macro</span></div>
              <h4 style={{ marginTop: 24 }}>Structure</h4>
              <div className="ide-snippet"><span>def primes_up_to</span><span className="badge">L2</span></div>
              <div className="ide-snippet"><span>↳ for i</span><span className="badge">L5</span></div>
              <div className="ide-snippet"><span>&nbsp;&nbsp;↳ for j</span><span className="badge">L7</span></div>
            </aside>

            <div className="ide-editor">
              {IDE_LINES.map((ln) => (
                <div
                  key={ln.n}
                  className={
                    "ide-line" +
                    (ln.n === cur.line ? " cursor" : "") +
                    (ln.bp ? " bp" : "")
                  }
                >
                  <span className="ide-num">{String(ln.n).padStart(2, "0")}</span>
                  <code dangerouslySetInnerHTML={{ __html: ln.html || "&nbsp;" }} />
                </div>
              ))}
            </div>

            <aside className="ide-right">
              <h4 style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--dim)" }}>
                Trace · step {step + 1}/{TRACE.length}
              </h4>
              {TRACE.map((t, i) => (
                <div key={i} className={"ide-trace-step" + (i === step ? " is-current" : "")}>
                  <span className="step-num">{String(i + 1).padStart(2, "0")}</span>
                  <div>
                    <div className="label">L{t.line} · {t.label}</div>
                    <div className="delta">{t.delta}</div>
                  </div>
                </div>
              ))}
            </aside>
          </div>

          <div className="ide-foot">
            <span>▸ <span className="tx">heartbeat</span> · 500ms · sandbox active · 5s wall · 512MB cap</span>
            <span className="ok">● 200+ tests passing · run #042</span>
          </div>
        </div>
      </div>
    </section>
  );
}

window.Voice = Voice;
window.IDE = IDE;
