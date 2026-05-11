/* global React */
const { useEffect, useState, useRef } = React;

// ────────────────────────────────────────────────────────────
// Sonification demo — rows of code sync with pitch bars below.
// A tiny WebAudio engine plays tones when the user hits play.
// ────────────────────────────────────────────────────────────

const SONIFY_CODE = [
  { kind: "kw",  indent: 0, html: '<span class="sonify-tok-cmt"># sieve of eratosthenes</span>' },
  { kind: "fn",  indent: 0, html: '<span class="sonify-tok-kw">def</span> <span class="sonify-tok-fn">primes_up_to</span>(<span class="sonify-tok-id">n</span>):' },
  { kind: "id",  indent: 1, html: '<span class="sonify-tok-id">sieve</span> = [<span class="sonify-tok-kw">True</span>] * (<span class="sonify-tok-id">n</span> + <span class="sonify-tok-num">1</span>)' },
  { kind: "id",  indent: 1, html: '<span class="sonify-tok-id">sieve</span>[<span class="sonify-tok-num">0</span>] = <span class="sonify-tok-id">sieve</span>[<span class="sonify-tok-num">1</span>] = <span class="sonify-tok-kw">False</span>' },
  { kind: "lp",  indent: 1, html: '<span class="sonify-tok-kw">for</span> <span class="sonify-tok-id">i</span> <span class="sonify-tok-kw">in</span> <span class="sonify-tok-fn">range</span>(<span class="sonify-tok-num">2</span>, <span class="sonify-tok-fn">int</span>(<span class="sonify-tok-id">n</span>**<span class="sonify-tok-num">0.5</span>) + <span class="sonify-tok-num">1</span>):' },
  { kind: "if",  indent: 2, html: '<span class="sonify-tok-kw">if</span> <span class="sonify-tok-id">sieve</span>[<span class="sonify-tok-id">i</span>]:' },
  { kind: "lp",  indent: 3, html: '<span class="sonify-tok-kw">for</span> <span class="sonify-tok-id">j</span> <span class="sonify-tok-kw">in</span> <span class="sonify-tok-fn">range</span>(<span class="sonify-tok-id">i</span>*<span class="sonify-tok-id">i</span>, <span class="sonify-tok-id">n</span>+<span class="sonify-tok-num">1</span>, <span class="sonify-tok-id">i</span>):' },
  { kind: "id",  indent: 4, html: '<span class="sonify-tok-id">sieve</span>[<span class="sonify-tok-id">j</span>] = <span class="sonify-tok-kw">False</span>' },
  { kind: "kw",  indent: 1, html: '<span class="sonify-tok-kw">return</span> [<span class="sonify-tok-id">i</span> <span class="sonify-tok-kw">for</span> <span class="sonify-tok-id">i</span>, <span class="sonify-tok-id">p</span> <span class="sonify-tok-kw">in</span> <span class="sonify-tok-fn">enumerate</span>(<span class="sonify-tok-id">sieve</span>) <span class="sonify-tok-kw">if</span> <span class="sonify-tok-id">p</span>]' },
];

// pitch in Hz: indent → A2..C5; kind → instrument family
const PITCH = [110, 165, 220, 330, 440, 660];
const TONE_FOR = { fn: "sine", lp: "triangle", if: "square", kw: "sawtooth", id: "sine" };
const TAG_FOR  = { fn: "function", lp: "loop", if: "branch", kw: "keyword", id: "stmt" };
const TAG_CLS  = { fn: "fn", lp: "lp", if: "if", kw: "kw", id: "" };

function Sonify() {
  const [step, setStep] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef(null);
  const timerRef = useRef(null);

  function ensureCtx() {
    if (!audioRef.current) {
      const C = window.AudioContext || window.webkitAudioContext;
      if (!C) return null;
      audioRef.current = new C();
    }
    return audioRef.current;
  }

  function playOne(line) {
    const ctx = ensureCtx();
    if (!ctx) return;
    const now = ctx.currentTime;
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = TONE_FOR[line.kind] || "sine";
    o.frequency.value = PITCH[Math.min(line.indent, PITCH.length - 1)];
    g.gain.setValueAtTime(0, now);
    g.gain.linearRampToValueAtTime(0.18, now + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0008, now + 0.42);
    o.connect(g).connect(ctx.destination);
    o.start(now);
    o.stop(now + 0.45);
  }

  function play() {
    setPlaying(true);
    setStep(0);
  }
  function stop() {
    setPlaying(false);
    setStep(-1);
    clearTimeout(timerRef.current);
  }

  useEffect(() => {
    if (!playing) return;
    if (step < 0) return;
    if (step >= SONIFY_CODE.length) {
      setPlaying(false);
      setStep(-1);
      return;
    }
    playOne(SONIFY_CODE[step]);
    timerRef.current = setTimeout(() => setStep((s) => s + 1), 520);
    return () => clearTimeout(timerRef.current);
    // eslint-disable-next-line
  }, [step, playing]);

  // ambient idle: quietly cycle the highlight even when not playing
  useEffect(() => {
    if (playing) return;
    if (document.body.classList.contains("no-motion")) return;
    let i = 0;
    const id = setInterval(() => {
      setStep(i % SONIFY_CODE.length);
      i++;
    }, 900);
    return () => clearInterval(id);
  }, [playing]);

  return (
    <section id="hear" className="sonify">
      <div className="wrap">
        <div className="reveal section-head">
          <div>
            <div className="eyebrow" style={{ marginBottom: 16 }}>01 — Sonification</div>
            <h2>
              Code becomes <span className="accent">music</span>.
            </h2>
          </div>
          <p className="desc">
            Pitch maps to indentation. Each construct gets its own timbre — sine for
            functions, triangle for loops, square for branches. Close your eyes
            and you can <em>feel</em> the shape of a program.
          </p>
        </div>

        <div className="reveal sonify-stage">
          <div className="sonify-code">
            {SONIFY_CODE.map((row, i) => (
              <div
                key={i}
                className={"sonify-row" + (i === step ? " active" : "")}
              >
                <span className="sonify-line">{String(i + 1).padStart(2, "0")}</span>
                <code style={{ paddingLeft: row.indent * 18 }} dangerouslySetInnerHTML={{ __html: row.html }} />
              </div>
            ))}
          </div>

          <div className="sonify-tones" aria-hidden="true" role="presentation">
            {SONIFY_CODE.map((row, i) => {
              const lvl = (PITCH[Math.min(row.indent, PITCH.length - 1)] - 110) / (660 - 110);
              return (
                <div key={i} className={"tone-row" + (i === step ? " active" : "")}>
                  <span>L{String(i + 1).padStart(2, "0")} ▸ in{row.indent}</span>
                  <div className="tone-pitch-bar">
                    <div
                      className="fill"
                      style={{
                        width: `${30 + lvl * 65}%`,
                        transform: i === step ? "scaleY(1.4)" : "scaleY(1)",
                      }}
                    />
                  </div>
                  <span className={"tone-tag " + TAG_CLS[row.kind]}>{TAG_FOR[row.kind]}</span>
                </div>
              );
            })}
          </div>

          <div className="sonify-controls">
            <div className="left">
              <button
                className="play-btn"
                onClick={playing ? stop : play}
                aria-label={playing ? "Stop sonification" : "Play sonification"}
              >
                {playing ? (
                  <svg viewBox="0 0 16 16"><rect x="3" y="3" width="3" height="10" /><rect x="10" y="3" width="3" height="10" /></svg>
                ) : (
                  <svg viewBox="0 0 16 16"><polygon points="3,2 14,8 3,14" /></svg>
                )}
              </button>
              <span>
                {playing
                  ? `▸ playing line ${step + 1} of ${SONIFY_CODE.length}`
                  : 'press play · "sonify block"'}
              </span>
            </div>
            <div className="sonify-meta">
              <b>9 tones</b> · range <b>A2 → E5</b> · alt+S
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

window.Sonify = Sonify;
