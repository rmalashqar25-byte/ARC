/* Keep startup visible independently of the optional opening animation. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else api.mount(root);
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';

  function mount(win) {
    const doc = win.document;
    const panel = doc.getElementById('arc-startup');
    if (!panel) return;
    const status = doc.getElementById('arc-startup-status');
    const retry = doc.getElementById('arc-startup-retry');
    let ready = false;
    let failed = false;
    const onSlow = () => {
      if (ready || failed) return;
      status.textContent = 'Still opening your workspace. You can try again if it takes too long.';
      retry.hidden = false;
    };
    const onError = () => {
      if (ready) return;
      failed = true;
      status.textContent = 'ARC could not open. Check your connection and try again.';
      retry.hidden = false;
      // An error must be visible even if the opening animation is still playing.
      win.dispatchEvent(new win.Event('arc-skip-intro'));
    };
    const onProgress = (event) => {
      if (!ready && !failed && event.detail === 'engine') {
        status.textContent = 'Preparing your workspace…';
      }
    };
    const onReady = () => {
      if (ready) return;
      ready = true;
      win.clearTimeout(timer);
      win.removeEventListener('flutter-first-frame', onReady);
      win.removeEventListener('arc-startup-error', onError);
      win.removeEventListener('arc-startup-progress', onProgress);
      panel.remove();
    };
    retry.addEventListener('click', () => win.location.reload());
    win.addEventListener('flutter-first-frame', onReady);
    win.addEventListener('arc-startup-error', onError);
    win.addEventListener('arc-startup-progress', onProgress);
    const timer = win.setTimeout(onSlow, 12000);
    return { onReady, onError, onSlow, onProgress };
  }

  return { mount };
});
