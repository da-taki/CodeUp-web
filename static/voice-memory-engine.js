'use strict';

(function () {
  const STATES = {
    IDLE: 'IDLE',
    LISTENING: 'LISTENING',
    PROCESSING: 'PROCESSING',
    RESPONDING: 'RESPONDING',
    SPEAKING: 'SPEAKING',
  };

  const VALID_TRANSITIONS = {
    IDLE: ['LISTENING'],
    LISTENING: ['PROCESSING', 'IDLE'],
    PROCESSING: ['RESPONDING', 'LISTENING', 'IDLE'],
    RESPONDING: ['SPEAKING', 'LISTENING', 'IDLE'],
    SPEAKING: ['LISTENING', 'IDLE'],
  };

  var DEVANAGARI_RE = /[\u0900-\u097F]/;
  var MICRO_CHUNK_SIZE = 22;

  var engine = {
    state: STATES.IDLE,
    abortController: null,
    requestLock: false,
    lastTranscript: '',
    lastTranscriptTime: 0,
    narrationQueue: [],
    narrationActive: false,
    interrupted: false,
    interruptTimestamp: 0,
    voiceActive: false,
    voiceLangMode: 'auto',
    conversationHistory: [],
    maxHistory: 20,
    streamBuffer: '',
    streamUpdateThrottle: null,
    spokenIndex: 0,
    renderedIndex: 0,
    fullStreamText: '',
    stateDebounce: null,
    onStateChange: null,
    onStreamChunk: null,
    onSyncUpdate: null,
    onResponseComplete: null,
    onError: null,
  };

  function setState(newState) {
    var prev = engine.state;
    if (prev === newState) return;
    var allowed = VALID_TRANSITIONS[prev];
    if (allowed && !allowed.includes(newState)) {
      return;
    }
    engine.state = newState;
    if (engine.onStateChange) {
      engine.onStateChange(newState, prev);
    }
  }

  function setStateDebounced(newState, delayMs) {
    if (engine.stateDebounce) {
      clearTimeout(engine.stateDebounce);
      engine.stateDebounce = null;
    }
    if (!delayMs || delayMs <= 0) {
      setState(newState);
      return;
    }
    engine.stateDebounce = setTimeout(function () {
      engine.stateDebounce = null;
      setState(newState);
    }, delayMs);
  }

  function cancelAllOutput() {
    engine.interrupted = true;
    engine.interruptTimestamp = Date.now();
    try { window.speechSynthesis.cancel(); } catch (e) {}
    if (engine.abortController) {
      engine.abortController.abort();
      engine.abortController = null;
    }
    engine.narrationQueue = [];
    engine.narrationActive = false;
    engine.streamBuffer = '';
    engine.spokenIndex = 0;
    engine.renderedIndex = 0;
    engine.fullStreamText = '';
    if (engine.streamUpdateThrottle) {
      clearTimeout(engine.streamUpdateThrottle);
      engine.streamUpdateThrottle = null;
    }
    if (engine.stateDebounce) {
      clearTimeout(engine.stateDebounce);
      engine.stateDebounce = null;
    }
  }

  function interrupt() {
    cancelAllOutput();
    engine.requestLock = false;
    setState(STATES.LISTENING);
  }

  function isStale(timestampBefore) {
    return timestampBefore < engine.interruptTimestamp;
  }

  function isDuplicate(transcript) {
    var normalized = transcript.trim().toLowerCase();
    if (!normalized) return true;
    var now = Date.now();
    if (normalized === engine.lastTranscript && (now - engine.lastTranscriptTime) < 3000) {
      return true;
    }
    engine.lastTranscript = normalized;
    engine.lastTranscriptTime = now;
    return false;
  }

  function addToHistory(role, content) {
    engine.conversationHistory.push({
      role: role,
      content: content.slice(0, 500),
      timestamp: Date.now(),
    });
    if (engine.conversationHistory.length > engine.maxHistory) {
      engine.conversationHistory = engine.conversationHistory.slice(-engine.maxHistory);
    }
  }

  function isHindiText(text) {
    return DEVANAGARI_RE.test(text);
  }

  function detectLang(text) {
    if (engine.voiceLangMode === 'en') return 'en-US';
    if (engine.voiceLangMode === 'hi') return 'hi-IN';
    return isHindiText(text) ? 'hi-IN' : 'en-US';
  }

  function pickVoice(lang) {
    if (!('speechSynthesis' in window)) return null;
    var voices = window.speechSynthesis.getVoices();
    if (!voices.length) return null;
    var prefix = lang.slice(0, 2);
    var exact = voices.find(function (v) { return v.lang === lang; });
    if (exact) return exact;
    var partial = voices.find(function (v) { return v.lang.startsWith(prefix); });
    if (partial) return partial;
    if (prefix === 'hi') {
      var indian = voices.find(function (v) { return v.lang === 'en-IN'; });
      if (indian) return indian;
    }
    return null;
  }

  function splitMixedLanguage(text) {
    var segments = [];
    var current = '';
    var currentIsHindi = null;
    var words = text.split(/(\s+)/);
    for (var i = 0; i < words.length; i++) {
      var word = words[i];
      if (!word) continue;
      if (/^\s+$/.test(word)) {
        current += word;
        continue;
      }
      var wordIsHindi = DEVANAGARI_RE.test(word);
      if (currentIsHindi === null) {
        currentIsHindi = wordIsHindi;
        current += word;
      } else if (wordIsHindi === currentIsHindi) {
        current += word;
      } else {
        if (current.trim()) segments.push({ text: current.trim(), lang: currentIsHindi ? 'hi-IN' : 'en-US' });
        current = word;
        currentIsHindi = wordIsHindi;
      }
    }
    if (current.trim()) segments.push({ text: current.trim(), lang: currentIsHindi ? 'hi-IN' : 'en-US' });
    return segments;
  }

  function speakSegment(text, lang) {
    return new Promise(function (resolve) {
      if (!text || !('speechSynthesis' in window)) {
        resolve();
        return;
      }
      var utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang || 'en-US';
      var voice = pickVoice(utterance.lang);
      if (voice) utterance.voice = voice;
      utterance.rate = 1;
      utterance.onend = function () {
        engine.spokenIndex += text.length;
        if (engine.onSyncUpdate) engine.onSyncUpdate(engine.spokenIndex, engine.renderedIndex);
        resolve();
      };
      utterance.onerror = function () {
        engine.spokenIndex += text.length;
        resolve();
      };
      window.speechSynthesis.speak(utterance);
    });
  }

  function speakSentence(text) {
    if (engine.voiceLangMode !== 'auto') {
      return speakSegment(text, detectLang(text));
    }
    var segments = splitMixedLanguage(text);
    if (segments.length <= 1) {
      return speakSegment(text, detectLang(text));
    }
    return segments.reduce(function (chain, seg) {
      return chain.then(function () {
        if (engine.interrupted) return;
        return speakSegment(seg.text, seg.lang);
      });
    }, Promise.resolve());
  }

  async function processNarrationQueue() {
    if (engine.narrationActive) return;
    engine.narrationActive = true;
    while (engine.narrationQueue.length > 0) {
      if (engine.interrupted) {
        engine.narrationQueue = [];
        break;
      }
      if (engine.state !== STATES.SPEAKING && engine.state !== STATES.RESPONDING) {
        engine.narrationQueue = [];
        break;
      }
      var sentence = engine.narrationQueue.shift();
      await speakSentence(sentence);
    }
    engine.narrationActive = false;
    if (engine.narrationQueue.length === 0 && engine.state === STATES.SPEAKING && !engine.interrupted) {
      if (engine.voiceActive) {
        setState(STATES.LISTENING);
      } else {
        setState(STATES.IDLE);
      }
    }
  }

  function enqueueSentence(sentence) {
    if (!sentence || !sentence.trim()) return;
    engine.narrationQueue.push(sentence.trim());
    if (engine.state === STATES.RESPONDING || engine.state === STATES.SPEAKING) {
      processNarrationQueue();
    }
  }

  function extractMicroChunks(buffer) {
    var chunks = [];
    var pattern = /[^.!?\n]+[.!?\n]+/g;
    var match;
    var lastIndex = 0;
    while ((match = pattern.exec(buffer)) !== null) {
      var sentence = match[0].trim();
      if (sentence.length <= MICRO_CHUNK_SIZE * 2) {
        chunks.push(sentence);
      } else {
        var words = sentence.split(/\s+/);
        var micro = '';
        for (var i = 0; i < words.length; i++) {
          var next = micro ? micro + ' ' + words[i] : words[i];
          if (next.length >= MICRO_CHUNK_SIZE && micro) {
            chunks.push(micro);
            micro = words[i];
          } else {
            micro = next;
          }
        }
        if (micro) chunks.push(micro);
      }
      lastIndex = match.index + match[0].length;
    }
    var remainder = buffer.slice(lastIndex);
    if (chunks.length === 0 && remainder.length > MICRO_CHUNK_SIZE) {
      var breakPoint = remainder.lastIndexOf(' ', MICRO_CHUNK_SIZE + 8);
      if (breakPoint > 8) {
        chunks.push(remainder.slice(0, breakPoint).trim());
        remainder = remainder.slice(breakPoint);
      }
    }
    return { chunks: chunks, remainder: remainder };
  }

  async function streamAIResponse(prompt, options) {
    if (engine.requestLock) return null;
    engine.requestLock = true;
    engine.interrupted = false;
    engine.spokenIndex = 0;
    engine.renderedIndex = 0;
    engine.fullStreamText = '';
    var startTs = Date.now();
    setState(STATES.PROCESSING);

    var controller = new AbortController();
    engine.abortController = controller;

    var langSel = (document.getElementById('languageSelector') || {}).value || 'en';
    var currentHtml = options.currentHtml || '';
    var projectId = options.projectId || '';

    addToHistory('user', prompt);

    try {
      var response = await fetch('/generate-code-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt,
          current_html: currentHtml,
          language: langSel,
          project_id: projectId,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error('Stream request failed: ' + response.status);
      }

      setStateDebounced(STATES.RESPONDING, 60);
      engine.streamBuffer = '';
      var fullResponse = '';
      var finalHtml = '';

      var reader = response.body.getReader();
      var decoder = new TextDecoder();
      var partialLine = '';

      while (true) {
        if (engine.interrupted) break;
        var result = await reader.read();
        if (result.done) break;
        if (controller.signal.aborted) break;
        if (isStale(startTs)) break;

        var text = decoder.decode(result.value, { stream: true });
        partialLine += text;
        var lines = partialLine.split('\n');
        partialLine = lines.pop() || '';

        for (var li = 0; li < lines.length; li++) {
          var line = lines[li];
          if (!line.startsWith('data: ')) continue;
          var payload = line.slice(6);
          try {
            var data = JSON.parse(payload);
            if (data.chunk) {
              fullResponse += data.chunk;
              engine.fullStreamText = fullResponse;
              engine.streamBuffer += data.chunk;

              if (engine.onStreamChunk && !isStale(startTs)) {
                if (engine.streamUpdateThrottle) {
                  clearTimeout(engine.streamUpdateThrottle);
                }
                var capturedFull = fullResponse;
                engine.streamUpdateThrottle = setTimeout(function () {
                  engine.streamUpdateThrottle = null;
                  if (!isStale(startTs) && engine.onStreamChunk) {
                    engine.renderedIndex = capturedFull.length;
                    engine.onStreamChunk(capturedFull, engine.spokenIndex);
                  }
                }, 35);
              }

              var extracted = extractMicroChunks(engine.streamBuffer);
              engine.streamBuffer = extracted.remainder;
              for (var ci = 0; ci < extracted.chunks.length; ci++) {
                enqueueSentence(extracted.chunks[ci]);
              }
            }
            if (data.done) {
              finalHtml = data.html || fullResponse;
            }
          } catch (e) {}
        }
      }

      if (engine.streamUpdateThrottle) {
        clearTimeout(engine.streamUpdateThrottle);
        engine.streamUpdateThrottle = null;
      }

      if (engine.interrupted || isStale(startTs)) {
        engine.requestLock = false;
        engine.abortController = null;
        return null;
      }

      if (engine.streamBuffer.trim()) {
        enqueueSentence(engine.streamBuffer);
        engine.streamBuffer = '';
      }

      if (engine.onStreamChunk) {
        engine.renderedIndex = fullResponse.length;
        engine.onStreamChunk(fullResponse, engine.spokenIndex);
      }

      setStateDebounced(STATES.SPEAKING, 80);
      addToHistory('assistant', fullResponse.slice(0, 500));

      if (engine.onResponseComplete) {
        engine.onResponseComplete(finalHtml || fullResponse, prompt);
      }

      await storeMemoryAfterResponse(prompt, finalHtml || fullResponse);

      engine.requestLock = false;
      engine.abortController = null;
      return finalHtml || fullResponse;
    } catch (error) {
      engine.requestLock = false;
      engine.abortController = null;
      if (error.name === 'AbortError') {
        setState(STATES.LISTENING);
        return null;
      }
      setState(STATES.IDLE);
      if (engine.onError) engine.onError(error);
      return null;
    }
  }

  async function chatWithContext(message, options) {
    if (engine.requestLock) return null;
    engine.requestLock = true;
    engine.interrupted = false;
    engine.spokenIndex = 0;
    engine.renderedIndex = 0;
    engine.fullStreamText = '';
    var startTs = Date.now();
    setState(STATES.PROCESSING);

    var controller = new AbortController();
    engine.abortController = controller;
    var langSel = (document.getElementById('languageSelector') || {}).value || 'en';

    addToHistory('user', message);

    try {
      var response = await fetch('/html-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          html: options.currentHtml || '',
          language: langSel,
        }),
        signal: controller.signal,
      });

      var data = await response.json();
      if (!data.success) throw new Error(data.error || 'Chat failed');

      if (isStale(startTs)) {
        engine.requestLock = false;
        engine.abortController = null;
        return null;
      }

      var reply = data.reply || '';
      engine.fullStreamText = reply;
      setStateDebounced(STATES.SPEAKING, 80);
      addToHistory('assistant', reply.slice(0, 500));

      var extracted = extractMicroChunks(reply + '\n');
      for (var i = 0; i < extracted.chunks.length; i++) {
        enqueueSentence(extracted.chunks[i]);
      }
      if (extracted.remainder.trim()) {
        enqueueSentence(extracted.remainder);
      }

      if (engine.onResponseComplete) {
        engine.onResponseComplete(reply, message);
      }

      await storeMemoryAfterResponse(message, reply);

      engine.requestLock = false;
      engine.abortController = null;
      return reply;
    } catch (error) {
      engine.requestLock = false;
      engine.abortController = null;
      if (error.name === 'AbortError') {
        setState(STATES.LISTENING);
        return null;
      }
      setState(STATES.IDLE);
      if (engine.onError) engine.onError(error);
      return null;
    }
  }

  async function storeMemoryAfterResponse(userInput, response) {
    var content = extractMemoryContent(userInput, response);
    if (!content) return;
    try {
      await fetch('/smart-memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: content.text,
          type: content.type,
        }),
      });
    } catch (e) {}
  }

  function extractMemoryContent(userInput, response) {
    var lower = userInput.toLowerCase();
    if (/\b(remember|note|important|always|never|prefer)\b/.test(lower)) {
      return { text: userInput, type: 'instruction' };
    }
    if (/\b(my name|i am|i'm|i live|my school|my class|my age)\b/.test(lower)) {
      return { text: userInput, type: 'fact' };
    }
    if (/\b(build|make|create)\b.*\b(website|site|page)\b/.test(lower)) {
      return { text: 'User requested: ' + userInput.slice(0, 200), type: 'context' };
    }
    if (userInput.length > 20) {
      return { text: userInput.slice(0, 200), type: 'context' };
    }
    return null;
  }

  function handleTranscript(transcript) {
    if (isDuplicate(transcript)) return false;
    if (engine.state === STATES.SPEAKING || engine.state === STATES.RESPONDING) {
      interrupt();
    }
    return true;
  }

  function getState() {
    return engine.state;
  }

  function getHistory() {
    return engine.conversationHistory.slice();
  }

  function setVoiceActive(active) {
    engine.voiceActive = !!active;
  }

  function setVoiceLangMode(mode) {
    if (mode === 'en' || mode === 'hi' || mode === 'auto') {
      engine.voiceLangMode = mode;
    }
  }

  function getVoiceLangMode() {
    return engine.voiceLangMode;
  }

  function resetEngine() {
    cancelAllOutput();
    engine.state = STATES.IDLE;
    engine.requestLock = false;
    engine.lastTranscript = '';
    engine.lastTranscriptTime = 0;
    engine.conversationHistory = [];
    engine.narrationQueue = [];
    engine.narrationActive = false;
    engine.interrupted = false;
    engine.interruptTimestamp = 0;
    engine.voiceActive = false;
    engine.streamBuffer = '';
    engine.spokenIndex = 0;
    engine.renderedIndex = 0;
    engine.fullStreamText = '';
  }

  window.VoiceMemoryEngine = {
    STATES: STATES,
    getState: getState,
    setState: setState,
    interrupt: interrupt,
    cancelAllOutput: cancelAllOutput,
    isDuplicate: isDuplicate,
    handleTranscript: handleTranscript,
    streamAIResponse: streamAIResponse,
    chatWithContext: chatWithContext,
    addToHistory: addToHistory,
    getHistory: getHistory,
    setVoiceActive: setVoiceActive,
    setVoiceLangMode: setVoiceLangMode,
    getVoiceLangMode: getVoiceLangMode,
    resetEngine: resetEngine,
    isHindiText: isHindiText,
    detectLang: detectLang,
    splitMixedLanguage: splitMixedLanguage,
    extractMicroChunks: extractMicroChunks,
    set onStateChange(fn) { engine.onStateChange = fn; },
    set onStreamChunk(fn) { engine.onStreamChunk = fn; },
    set onSyncUpdate(fn) { engine.onSyncUpdate = fn; },
    set onResponseComplete(fn) { engine.onResponseComplete = fn; },
    set onError(fn) { engine.onError = fn; },
    get onStateChange() { return engine.onStateChange; },
    get onStreamChunk() { return engine.onStreamChunk; },
    get onSyncUpdate() { return engine.onSyncUpdate; },
    get onResponseComplete() { return engine.onResponseComplete; },
    get onError() { return engine.onError; },
  };
})();
