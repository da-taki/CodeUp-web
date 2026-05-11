/* global React */
const { useEffect, useState, useRef } = React;

// ────────────────────────────────────────────────────────────
// Reveal-on-scroll
// ────────────────────────────────────────────────────────────
function useReveal() {
  useEffect(() => {
    const els = document.querySelectorAll(".reveal");
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12 }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
}

// ────────────────────────────────────────────────────────────
// Top nav
// ────────────────────────────────────────────────────────────
function Nav() {
  return (
    <nav className="nav">
      <a className="nav-brand" href="#top">
        <span className="dot"></span>
        CodeUp<span style={{ color: "var(--dim)", marginLeft: 4 }}>/v0.8.0</span>
      </a>
      <div className="nav-links">
        <a href="#hear">Hear</a>
        <a href="#speak">Speak</a>
        <a href="#ide">IDE</a>
        <a href="#features">Features</a>
        <a href="#manifesto">Manifesto</a>
      </div>
      <a className="nav-cta" href="/ide">
        Open the IDE <span aria-hidden="true">→</span>
      </a>
    </nav>
  );
}

// ────────────────────────────────────────────────────────────
// Hero waveform — animated bars driven by sin/cos
// ────────────────────────────────────────────────────────────
function Waveform({ count = 96 }) {
  const [t, setT] = useState(0);
  const noMotion = useRef(false);
  useEffect(() => {
    noMotion.current = document.body.classList.contains("no-motion");
    if (noMotion.current) return;
    let raf;
    let last = performance.now();
    const tick = (now) => {
      const dt = (now - last) / 1000;
      last = now;
      setT((v) => v + dt);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const bars = [];
  for (let i = 0; i < count; i++) {
    const x = i / count;
    // a code-like silhouette: peaks at function "openings"
    const env =
      0.55 +
      0.35 * Math.sin(x * Math.PI * 1.6 + t * 0.6) +
      0.18 * Math.sin(x * Math.PI * 5.7 + t * 1.2) +
      0.12 * Math.sin(x * Math.PI * 13 + t * 2.4);
    const h = Math.max(0.06, Math.min(1, env)) * 100;
    const isAccent = i % 11 === 3 || i % 13 === 7;
    bars.push(
      <div
        key={i}
        className={"bar" + (isAccent ? " accent" : "")}
        style={{ height: `${h}%` }}
      ></div>
    );
  }
  return <div className="hero-wave" aria-hidden="true" role="presentation">{bars}</div>;
}

// ────────────────────────────────────────────────────────────
// Hero
// ────────────────────────────────────────────────────────────
function Hero() {
  return (
    <section id="top" className="hero" aria-labelledby="hero-heading">
      {/* Second skip link — only visible/reachable after the editor-hero one,
          so screen reader users have an explicit way past the decorative
          waveform and ticker without tabbing through every animated element. */}
      <a href="#features" className="skip-link" style={{top: '40px'}}>Skip decorative hero</a>
      <div className="hero-grid-bg" aria-hidden="true" role="presentation"></div>
      <div className="wrap hero-top">
        <div className="meta">
          <span><b>blind-first</b> python ide</span>
          <span>est. <b>2025</b></span>
          <span>license <b>MIT</b></span>
        </div>
        <div className="meta">
          <span>EN · हिं</span>
          <span><b>200+</b> tests</span>
        </div>
      </div>

      <div className="wrap hero-headline">
        <div className="hero-eyebrow-row">
          <span className="version-pill">
            <span className="blip"></span> v0.8.0 · COFFEE
          </span>
          <span className="eyebrow">Built for ears, hands, and voice</span>
        </div>
        <h1 className="h1">
          Code<span className="accent">.</span>
          <br />
          <span className="stroke">you can</span> hear<span className="accent">.</span>
        </h1>
        <p className="hero-tagline">
          A Python IDE where every core feature — navigation, execution, debugging,
          code understanding — works through <em>audio</em>, <em>keyboard</em>,
          and <em>natural language</em>. Not retrofitted accessibility.
          Non-visual is the default.
        </p>
        <div className="hero-cta-row">
          <a className="btn btn-primary" href="/ide">
            Open the IDE <span className="arrow">→</span>
          </a>
          <a className="btn btn-ghost" href="#hear">
            Listen to a function first
          </a>
        </div>
      </div>

      <Waveform count={120} />

      <Ticker />
    </section>
  );
}

// ────────────────────────────────────────────────────────────
// Voice command marquee
// ────────────────────────────────────────────────────────────
function Ticker() {
  // aria-hidden — this is a decorative scrolling marquee. Real command list
  // lives in the Voice section below with semantic markup.
  const cmds = [
    'run', 'go to line twenty five', 'sonify block', 'tell the story',
    'चलाओ', 'what changed here', 'set breakpoint at line 10',
    'मदद', 'find variable x', 'explain simply', 'remember this as quick sort',
    'कोड समझाओ', 'next step', 'bookmark this', 'quiz me on loops',
    'live input mode', 'लाइन बीस पर जाओ', 'check for errors'
  ];
  const items = [...cmds, ...cmds];
  return (
    <div className="ticker" aria-hidden="true">
      <div className="ticker-track">
        {items.map((c, i) => (
          <React.Fragment key={i}>
            <span><span className="quote">"{c}"</span></span>
            <span className="sep">●</span>
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { Nav, Hero, useReveal });
