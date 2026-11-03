{{flutter_js}}
{{flutter_build_config}}

// Serve the renderer with ARC instead of waiting on an external CDN.
_flutter.loader.load({
  config: { canvasKitBaseUrl: 'canvaskit/' },
  onEntrypointLoaded: async function (engineInitializer) {
    try {
      window.dispatchEvent(new CustomEvent('arc-startup-progress', { detail: 'engine' }));
      const appRunner = await engineInitializer.initializeEngine();
      await appRunner.runApp();
    } catch (_) {
      window.dispatchEvent(new Event('arc-startup-error'));
    }
  }
}).catch(function () {
  window.dispatchEvent(new Event('arc-startup-error'));
});
