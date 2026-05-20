(function attachPywebviewApiBridge(global) {
  const DEFAULT_TIMEOUT_MS = 15000;
  const DEFAULT_INTERVAL_MS = 50;

  function readApi() {
    return global.pywebview && global.pywebview.api ? global.pywebview.api : null;
  }

  function waitForApi(options = {}) {
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const intervalMs = options.intervalMs ?? DEFAULT_INTERVAL_MS;
    const shouldWait = options.wait ?? true;

    const immediateApi = readApi();
    if (immediateApi) {
      return Promise.resolve(immediateApi);
    }

    if (!shouldWait) {
      return Promise.reject(new Error('PyWebView API is not ready'));
    }

    return new Promise((resolve, reject) => {
      const startedAt = Date.now();
      let settled = false;
      let intervalId = null;
      let timeoutId = null;

      const cleanup = () => {
        if (intervalId !== null) {
          clearInterval(intervalId);
        }
        if (timeoutId !== null) {
          clearTimeout(timeoutId);
        }
        global.removeEventListener('pywebviewready', onReady);
      };

      const finish = (callback) => {
        if (settled) {
          return;
        }
        settled = true;
        cleanup();
        callback();
      };

      const tryResolve = () => {
        const api = readApi();
        if (api) {
          finish(() => resolve(api));
        }
      };

      const onReady = () => {
        tryResolve();
      };

      global.addEventListener('pywebviewready', onReady);
      intervalId = setInterval(tryResolve, intervalMs);
      timeoutId = setTimeout(() => {
        finish(() => {
          reject(
            new Error(
              `PyWebView API is not ready after ${Date.now() - startedAt}ms`
            )
          );
        });
      }, timeoutMs);

      tryResolve();
    });
  }

  global.getPywebviewApi = waitForApi;
})(window);
