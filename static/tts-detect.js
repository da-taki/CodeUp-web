'use strict';

(function () {
  // Detect available speech synthesis voices and warn if Hindi is requested
  // but unavailable. Voices load asynchronously in some browsers.

  let voicesChecked = false;
  let hindiAvailable = false;

  function checkVoices() {
    if (!('speechSynthesis' in window)) {
      window._ttsAvailable = false;
      window._hindiTtsAvailable = false;
      voicesChecked = true;
      return;
    }
    const voices = window.speechSynthesis.getVoices();
    if (voices.length === 0) return; // not loaded yet
    hindiAvailable = voices.some(v => v.lang && v.lang.toLowerCase().startsWith('hi'));
    window._ttsAvailable = true;
    window._hindiTtsAvailable = hindiAvailable;
    voicesChecked = true;
    console.log('TTS voices loaded. Hindi available:', hindiAvailable);
  }

  // Try immediately and on the voiceschanged event
  checkVoices();
  if ('speechSynthesis' in window) {
    window.speechSynthesis.addEventListener('voiceschanged', checkVoices);
    // Some browsers never fire voiceschanged — poll once after 1s
    setTimeout(checkVoices, 1000);
  }

  // Helper for app.js to check before speaking Hindi
  window.warnIfHindiUnavailable = function (selectedLang) {
    if (selectedLang !== 'hi') return;
    if (!voicesChecked) return; // haven't checked yet, give it benefit of the doubt
    if (!hindiAvailable) {
      const msg = 'Hindi voice is not installed on this device. Narration will use the default voice. ' +
                  'For best results, install a Hindi text-to-speech voice in your operating system settings.';
      console.warn(msg);

      // Play a distinct two-tone alert before speaking so a Hindi-only user
      // who doesn't understand the English warning still knows something is
      // off — falling pitch suggests "missing/unavailable".
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        [880, 440].forEach((freq, i) => {
          setTimeout(() => {
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            gain.gain.value = 0.1;
            osc.frequency.value = freq;
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.15);
          }, i * 200);
        });
      } catch (e) {}

      // Speak the warning in English so the user actually hears it
      try {
        const u = new SpeechSynthesisUtterance(msg);
        u.lang = 'en-US';
        u.rate = 1;
        setTimeout(() => window.speechSynthesis.speak(u), 600);
      } catch (e) {}

      // Also show it in the output panel
      const out = document.getElementById('output');
      if (out) {
        out.textContent = '⚠ ' + msg + '\n\n' + (out.textContent || '');
      }
    }
  };

  // Detect speech recognition support
  window._speechRecognitionAvailable = !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  if (!window._speechRecognitionAvailable) {
    console.warn('Speech recognition not supported in this browser. Voice input disabled.');
  }
}());