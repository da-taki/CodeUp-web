/* global React, ReactDOM, Nav, Hero, Sonify, Voice, IDE, Features, Stats, CTA, Foot, useReveal, TweaksPanel, useTweaks, TweakSection, TweakRadio, TweakToggle */
const { useEffect } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "paper",
  "motion": true,
  "grain": true
}/*EDITMODE-END*/;

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  useReveal();

  useEffect(() => {
    const b = document.body;
    b.classList.remove("theme-paper", "theme-night", "theme-contrast");
    b.classList.add("theme-" + t.theme);
    b.classList.toggle("no-motion", !t.motion);
    b.classList.toggle("no-grain", !t.grain);
  }, [t.theme, t.motion, t.grain]);

  return (
    <React.Fragment>
      <Nav />
      <EditorHero />
      <Hero />
      <Sonify />
      <Voice />
      <IDE />
      <Features />
      <Stats />
      <CTA />
      <Foot />

      <TweaksPanel title="Tweaks">
        <TweakSection title="Theme">
          <TweakRadio
            label="Palette"
            value={t.theme}
            onChange={(v) => setTweak("theme", v)}
            options={[
              { value: "paper",    label: "Paper" },
              { value: "night",    label: "Night" },
              { value: "contrast", label: "High contrast" },
            ]}
          />
        </TweakSection>
        <TweakSection title="Motion">
          <TweakToggle
            label="Animations"
            value={t.motion}
            onChange={(v) => setTweak("motion", v)}
          />
          <TweakToggle
            label="Paper grain"
            value={t.grain}
            onChange={(v) => setTweak("grain", v)}
          />
        </TweakSection>
      </TweaksPanel>
    </React.Fragment>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
