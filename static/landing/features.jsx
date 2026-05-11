/* global React */
const { useEffect, useState } = React;

// ────────────────────────────────────────────────────────────
// Features grid + manifesto + stats + CTA + footer
// ────────────────────────────────────────────────────────────

function Features() {
  return (
    <section id="features" className="features">
      <div className="wrap">
        <div className="reveal section-head">
          <div>
            <div className="eyebrow" style={{ marginBottom: 16 }}>04 — Features</div>
            <h2>Built <span className="accent">end to end.</span></h2>
          </div>
          <p className="desc">
            Sandbox, sonifier, intent parser, audio debugger, AI mentor, bilingual
            UI, six-step tutorial. None of it is bolted on — every layer was
            written with non-visual interaction as the assumption.
          </p>
        </div>

        <div className="feat-grid">
          <div className="reveal feat span6">
            <div className="feat-num">F.01 / sonification</div>
            <h3>Pitch maps to indent. Timbre maps to construct.</h3>
            <p>Functions sing in sine. Loops in triangle. Branches in square. The Web Audio engine renders the AST as a 9-tone phrase you can recognise on second hearing.</p>
            <div className="feat-art"><div className="eq"><span></span><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div></div>
          </div>

          <div className="reveal delay-1 feat span6">
            <div className="feat-num">F.02 / voice</div>
            <h3>Grammar parser, not exact-match.</h3>
            <p>"go to line twenty five," "लाइन बीस पर जाओ," "set breakpoint at line 10" — all parsed to structured intents with slots. Hindi number words 0–50 are recognised in line-navigation commands.</p>
            <div className="feat-art"><div className="pulse-art"><div className="ring"></div><div className="ring"></div><div className="ring"></div><div className="core"></div></div></div>
          </div>

          <div className="reveal feat span4">
            <div className="feat-num">F.03 / sandbox</div>
            <h3>Subprocess isolation by default.</h3>
            <p>Per-session workspace. Restricted built-ins. RLIMIT_AS · RLIMIT_CPU on POSIX. eval/exec/open blocked. AST audit before execution.</p>
            <div className="feat-art">
              <div className="sandbox-art">
                <div className="row"><span>wall clock</span><b>5s</b></div>
                <div className="bar"><div className="fill"></div></div>
                <div className="row" style={{ marginTop: 10 }}><span>memory cap</span><b>512MB</b></div>
                <div className="bar"><div className="fill" style={{ animationDelay: "0.6s" }}></div></div>
                <div className="row" style={{ marginTop: 10 }}><span>trace events</span><b>5,000</b></div>
                <div className="bar"><div className="fill" style={{ animationDelay: "1.2s" }}></div></div>
              </div>
            </div>
          </div>

          <div className="reveal delay-1 feat span4">
            <div className="feat-num">F.04 / bilingual</div>
            <h3>EN ⇄ हिंदी, baked in.</h3>
            <p>Speech recognition switches between en-US and hi-IN automatically. Around 15 core Hindi commands cover the run/navigate/explain loop.</p>
            <div className="feat-art">
              <div className="bil-art">
                <div className="en">
                  <span>english</span>
                  <b>"run"</b>
                </div>
                <div className="arrow">⇄</div>
                <div className="hi">
                  <span>हिंदी</span>
                  <b>"चलाओ"</b>
                </div>
              </div>
            </div>
          </div>

          <div className="reveal delay-2 feat span4">
            <div className="feat-num">F.05 / pitch ladder</div>
            <h3>Indent, you can hear.</h3>
            <p>Six tones. Each level of nesting moves you up the ladder.</p>
            <div className="feat-art">
              <div className="ladder">
                <div className="row"><div className="lvl" style={{ width: "20%" }}></div><span className="lab">in 0</span></div>
                <div className="row"><div className="lvl" style={{ width: "35%" }}></div><span className="lab">in 1</span></div>
                <div className="row"><div className="lvl" style={{ width: "50%" }}></div><span className="lab">in 2</span></div>
                <div className="row"><div className="lvl" style={{ width: "70%" }}></div><span className="lab">in 3</span></div>
                <div className="row"><div className="lvl" style={{ width: "100%" }}></div><span className="lab">in 4</span></div>
              </div>
            </div>
          </div>

          <div className="reveal feat span12" id="manifesto">
            <div className="feat-num">F.06 / manifesto</div>
            <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr 1fr", gap: 32 }}>
              <div>
                <h3 style={{ fontSize: 36, lineHeight: 1.05 }}>
                  Accessibility isn't a settings panel.
                  <br />
                  <span style={{ color: "var(--accent)", fontStyle: "italic" }}>It's the architecture.</span>
                </h3>
                <p style={{ marginTop: 16 }}>
                  Every dialog is an inline modal with focus management — no
                  <code style={{ fontFamily: "var(--font-mono)" }}> window.prompt </code> anywhere.
                  Every feature reaches by keyboard. <kbd style={{ fontFamily: "var(--font-mono)", padding: "2px 6px", border: "1px solid var(--rule-strong)", borderRadius: 4 }}>Esc</kbd> stops speech mid-sentence. AI is optional. The CDN is empty.
                </p>
              </div>
              <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 12, fontFamily: "var(--font-mono)", fontSize: 13 }}>
                <li>● NVDA, JAWS, VoiceOver via aria-live</li>
                <li>● Protanopia · Deuteranopia · Tritanopia</li>
                <li>● High contrast + dyslexia mode</li>
                <li>● Atkinson Hyperlegible bundled</li>
                <li>● prefers-reduced-motion respected</li>
              </ul>
              <ul style={{ listStyle: "none", display: "flex", flexDirection: "column", gap: 12, fontFamily: "var(--font-mono)", fontSize: 13 }}>
                <li>● Monaco vendored — no CDN</li>
                <li>● Fonts vendored — no CDN</li>
                <li>● AI = optional, network = optional</li>
                <li>● 200+ tests, full isolation</li>
                <li>● MIT license</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function Stats() {
  return (
    <section className="stats">
      <div className="stats-grid">
        <div className="reveal stat">
          <div className="num">200<span className="accent">+</span></div>
          <div className="lbl">Tests passing</div>
        </div>
        <div className="reveal delay-1 stat">
          <div className="num">15<span className="accent">+</span></div>
          <div className="lbl">Hindi commands</div>
        </div>
        <div className="reveal delay-2 stat">
          <div className="num">5<span className="accent">k</span></div>
          <div className="lbl">Trace events / run</div>
        </div>
        <div className="reveal delay-3 stat">
          <div className="num">6<span className="accent">/6</span></div>
          <div className="lbl">Tutorial steps</div>
        </div>
        <div className="reveal stat">
          <div className="num">0<span className="accent">.</span></div>
          <div className="lbl">CDN dependencies</div>
        </div>
      </div>
    </section>
  );
}

function CTA() {
  return (
    <section className="cta">
      <div className="reveal">
        <h2>
          Press play.
          <br />
          <span className="accent">Listen to your code.</span>
        </h2>
        <p>
          CodeUp v0.8.0 — coffee theme. Independently developed by Taknoor Singh.
          Intended for schools and accessibility programs.
        </p>
        <div className="cta-row">
          <a className="btn btn-primary" href="/ide">
            Open the IDE <span className="arrow">→</span>
          </a>
          <a className="btn btn-ghost" href="https://github.com/da-taki/Code_Up" target="_blank" rel="noreferrer">
            View on GitHub
          </a>
          <a className="btn btn-ghost" href="https://github.com/da-taki/Code_Up#quickstart" target="_blank" rel="noreferrer">
            Read quickstart
          </a>
        </div>
      </div>
    </section>
  );
}

function Foot() {
  return (
    <footer>
      <div>
        © 2025 · <a href="https://github.com/da-taki" target="_blank" rel="noreferrer">@da-taki</a> · MIT
      </div>
      <div className="meta">
        <span>v0.8.0 · coffee</span>
        <span>built with monaco · web audio · web speech</span>
        <a href="https://github.com/da-taki/Code_Up">github.com/da-taki/Code_Up ↗</a>
      </div>
    </footer>
  );
}

window.Features = Features;
window.Stats = Stats;
window.CTA = CTA;
window.Foot = Foot;
