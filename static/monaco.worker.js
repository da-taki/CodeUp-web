try {
  importScripts('/static/vendor/monaco/min/vs/base/worker/workerMain.js');
} catch (e) {
  console.warn('Monaco worker failed to load. Syntax highlighting may be unavailable.', e);
}