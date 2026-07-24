'use strict';
(function () {
  var basePath = '/static/vendor/monaco/vs';
  // Use same-origin worker files so Monaco works under the app CSP.
  var workers = {
    json: basePath + '/json.worker-BizpAl9O.js',
    css: basePath + '/css.worker-CyhWkhHo.js',
    scss: basePath + '/css.worker-CyhWkhHo.js',
    less: basePath + '/css.worker-CyhWkhHo.js',
    html: basePath + '/html.worker-CA3iAimZ.js',
    handlebars: basePath + '/html.worker-CA3iAimZ.js',
    razor: basePath + '/html.worker-CA3iAimZ.js',
    javascript: basePath + '/ts.worker-2QLmBukE.js',
    typescript: basePath + '/ts.worker-2QLmBukE.js',
    defaultWorker: basePath + '/editorWorkerHost-fVE1cjcC.js',
  };
  window.MonacoEnvironment = {
    getWorkerUrl: function (_moduleId, label) {
      return workers[label] || workers.defaultWorker;
    },
  };
  window.__codeupMonacoReady = new Promise(function (resolve) {
    function fail(reason) {
      window.__codeupMonacoLoadError = reason || 'Monaco could not load.';
      resolve(null);
    }
    if (!window.require || !window.require.config) {
      fail('Monaco AMD loader is unavailable.');
      return;
    }
    try {
      window.require.config({ paths: { vs: basePath } });
      window.require(['vs/editor/editor.main'], function () {
        if (window.monaco && window.monaco.editor) {
          resolve(window.monaco);
        } else {
          fail('Monaco editor API did not initialize.');
        }
      }, function (error) {
        fail(error && error.message ? error.message : 'Monaco editor modules failed to load.');
      });
    } catch (error) {
      fail(error && error.message ? error.message : 'Monaco initialization failed.');
    }
  });
})();
