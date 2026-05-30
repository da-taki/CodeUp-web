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

  const engine = {
    state: STATES.IDLE,
    abortController: null,
    requestLock: false,
    lastTranscript: '',
    lastTranscriptTime: 0,
    narrationQueue: [],
    narrationActive: false,
    interrupted: false,
    voiceActive: false,
    conversationHistory: [],
    maxHistory: 20,
    streamBuffer: '',
    streamUpdateThrottle: null,
    onStateChange: null,
    onStreamChunk: null,
    onResponseComplete: null,
    onError: null,
  };

  function setState(newState) {
    const prev = engine.state;
    if (prev === newState) return;
    const allowed = VALID_TRANSITIONS[prev];
    if (allowed && !allowed.includes(newState)) {
      return;
    }
    engine.state = newState;
    if (engine.onStateChange) {
      engine.onStateChange(newState, prev);
    }
  }

  function cancelAllOutput() {
    engine.interrupted = true;
    try { window.speechSynthesis.cancel(); } catch (e) {}
    if (engine.abortController) {
      engine.abortController.abort();
      engine.abortController = null;
    }
    engine.narrationQueue = [];
    engine.narrationActive = false;
    engine.streamBuffer = '';
    if (engine.streamUpdateThrottle) {
      clearTimeout(engine.streamUpdateThrottle);
      engine.streamUpdateThrottle = null;
    }
  }

  function interrupt() {
    cancelAllOutput();
    engine.requestLock = false;
    setState(STATES.LISTENING);
  }

  function isDuplicate(transcript) {
    const normalized = transcript.trim().toLowerCase();
    if (!normalized) return true;
    const now = Date.now();
    if (normalized === engine.lastTranscript && (now - engine.lastTranscriptTime) < 3000) {
      return true;
    }
    engine.lastTranscript = normalized;
    engine.lastTranscriptTime = now;
    return false;
  }

  function addToHistory(role, content) {
    engine.conversationHistory.push({
      role,
      content: content.slice(0, 500),
      timestamp: Date.now(),
    });
    if (engine.conversationHistory.length > engine.maxHistory) {
      engine.conversationHistory = engine.conversationHistory.slice(-engine.maxHistory);
    }
  }

  function speakSentence(text) {
    return new Promise(function (resolve) {
      if (!text || !('speechSynthesis' in window)) {
        resolve();
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = (document.getElementById('languageSelector') || {}).value === 'hi' ? 'hi-IN' : 'en-US';
      utterance.rate = 1;
      utterance.onend = resolve;
      utterance.onerror = resolve;
      window.speechSynthesis.speak(utterance);
    });
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
      const sentence = engine.narrationQueue.shift();
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

  function extractSentences(buffer) {
    const sentences = [];
    const pattern = /[^.!?\n]+[.!?\n]+/g;
    let match;
    let lastIndex = 0;
    while ((match = pattern.exec(buffer)) !== null) {
      sentences.push(match[0].trim());
      lastIndex = match.index + match[0].length;
    }
    let remainder = buffer.slice(lastIndex);
    if (sentences.length === 0 && remainder.length > 40) {
      const breakPoint = remainder.lastIndexOf(' ', 40);
      if (breakPoint > 10) {
        sentences.push(remainder.slice(0, breakPoint).trim());
        remainder = remainder.slice(breakPoint);
      }
    }
    return { sentences, remainder };
  }

  async function streamAIResponse(prompt, options) {
    if (engine.requestLock) return null;
    engine.requestLock = true;
    engine.interrupted = false;
    setState(STATES.PROCESSING);

    const controller = new AbortController();
    engine.abortController = controller;

    const lang = (document.getElementById('languageSelector') || {}).value || 'en';
    const currentHtml = options.currentHtml || '';

    addToHistory('user', prompt);

    try {
      const response = await fetch('/generate-code-stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt,
          current_html: currentHtml,
          language: lang,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error('Stream request failed: ' + response.status);
      }

      setState(STATES.RESPONDING);
      engine.streamBuffer = '';
      let fullResponse = '';
      let finalHtml = '';

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let partialLine = '';

      while (true) {
        if (engine.interrupted) break;
        const { done, value } = await reader.read();
        if (done) break;
        if (controller.signal.aborted) break;

        const text = decoder.decode(value, { stream: true });
        partialLine += text;
        const lines = partialLine.split('\n');
        partialLine = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6);
          try {
            const data = JSON.parse(payload);
            if (data.chunk) {
              fullResponse += data.chunk;
              engine.streamBuffer += data.chunk;

              if (engine.onStreamChunk) {
                if (engine.streamUpdateThrottle) {
                  clearTimeout(engine.streamUpdateThrottle);
                }
                engine.streamUpdateThrottle = setTimeout(function () {
                  engine.streamUpdateThrottle = null;
                  if (engine.onStreamChunk) engine.onStreamChunk(fullResponse);
                }, 35);
              }

              const { sentences, remainder } = extractSentences(engine.streamBuffer);
              engine.streamBuffer = remainder;
              for (const s of sentences) {
                enqueueSentence(s);
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

      if (engine.interrupted) {
        engine.requestLock = false;
        engine.abortController = null;
        return null;
      }

      if (engine.streamBuffer.trim()) {
        enqueueSentence(engine.streamBuffer);
        engine.streamBuffer = '';
      }

      if (engine.onStreamChunk) {
        engine.onStreamChunk(fullResponse);
      }

      setState(STATES.SPEAKING);
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
    setState(STATES.PROCESSING);

    const controller = new AbortController();
    engine.abortController = controller;
    const lang = (document.getElementById('languageSelector') || {}).value || 'en';

    addToHistory('user', message);

    try {
      const response = await fetch('/html-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          html: options.currentHtml || '',
          language: lang,
        }),
        signal: controller.signal,
      });

      const data = await response.json();
      if (!data.success) throw new Error(data.error || 'Chat failed');

      const reply = data.reply || '';
      setState(STATES.SPEAKING);
      addToHistory('assistant', reply.slice(0, 500));

      const sentences = reply.match(/[^.!?\n]+[.!?\n]*/g) || [reply];
      for (const s of sentences) {
        enqueueSentence(s);
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
    const content = extractMemoryContent(userInput, response);
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
    const lower = userInput.toLowerCase();
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
    engine.voiceActive = false;
    engine.streamBuffer = '';
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
    resetEngine: resetEngine,
    set onStateChange(fn) { engine.onStateChange = fn; },
    set onStreamChunk(fn) { engine.onStreamChunk = fn; },
    set onResponseComplete(fn) { engine.onResponseComplete = fn; },
    set onError(fn) { engine.onError = fn; },
    get onStateChange() { return engine.onStateChange; },
    get onStreamChunk() { return engine.onStreamChunk; },
    get onResponseComplete() { return engine.onResponseComplete; },
    get onError() { return engine.onError; },
  };
})();
