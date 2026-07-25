(function () {
  const api = {
    isAvailable() {
      return Boolean(window.monaco && window.monaco.editor);
    },
    getTextareaFallbackIds() {
      return ['htmlEditor', 'cssEditor', 'jsEditor'];
    },
  };

  window.CodeUpMonacoLoader = api;
})();