/* ARC opening: projected geometry, no third-party assets or rendering library. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else api.mount(root);
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const SEEN_KEY = 'arc.opening.v1';
  const LENGTH = 3500;
  const REVEAL = 850;
  const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v));
  const smooth = (v) => { v = clamp(v); return v * v * (3 - 2 * v); };
  const mix = (a, b, t) => a + (b - a) * t;

  function project(point, tilt, turn, scale, center) {
    const [x, y, z] = point;
    const yy = y * Math.cos(tilt) - z * Math.sin(tilt);
    const zz = y * Math.sin(tilt) + z * Math.cos(tilt);
    const xx = x * Math.cos(turn) - yy * Math.sin(turn);
    const rotatedY = x * Math.sin(turn) + yy * Math.cos(turn);
    const perspective = 3.8 / (3.8 - zz * .42);
    return { x: center.x + xx * scale * perspective,
      y: center.y + rotatedY * scale * perspective, z: zz, perspective };
  }

  function frameAt(milliseconds) {
    const t = clamp(milliseconds / LENGTH);
    const gather = smooth((t - .31) / .43);
    const joined = smooth((t - .72) / .18);
    return { t, appear: smooth(t / .16), gather, joined,
      distance: mix(1.34, 0, gather),
      angle: -.42 + t * 3.25,
      ringAlpha: smooth((t - .07) / .27) * (1 - joined * .2),
      core: joined,
    };
  }

  function shouldPlay(storage, reducedMotion, preview) {
    if (reducedMotion) return false;
    if (preview) return true;
    try { return storage.getItem(SEEN_KEY) !== 'seen'; }
    catch (_) { return true; }
  }

  function mount(win) {
    const doc = win.document;
    const overlay = doc.getElementById('arc-intro');
    if (!overlay) return;
    const media = win.matchMedia('(prefers-reduced-motion: reduce)');
    const preview = new win.URLSearchParams(win.location.search).get('intro') === 'preview';
    let storage;
    try { storage = win.localStorage; } catch (_) { storage = null; }
    if (!shouldPlay(storage, media.matches, preview)) { overlay.remove(); return; }
    const canvas = doc.getElementById('arc-intro-canvas');
    let ctx;
    try { ctx = canvas.getContext('2d', { alpha: false }); } catch (_) { ctx = null; }
    if (!ctx) { overlay.remove(); return; }
    const skip = doc.getElementById('arc-intro-skip');
    const status = doc.getElementById('arc-intro-status');
    const progress = doc.getElementById('arc-intro-progress');
    const retry = doc.getElementById('arc-intro-retry');
    const html = doc.documentElement;
    html.dataset.arcIntro = 'playing';
    const blocked = new Map();
    const blockApp = () => {
      for (const element of doc.body.children) {
        if (element === overlay || ['SCRIPT', 'STYLE', 'LINK'].includes(element.tagName)) continue;
        if (!blocked.has(element)) { blocked.set(element, element.inert); element.inert = true; }
      }
    };
    blockApp();
    const observer = new win.MutationObserver(blockApp);
    observer.observe(doc.body, { childList: true });
    let width = 1, height = 1, ratio = 1;
    let elapsed = 0, last = null, raf = null, ready = false;
    let opening = null, finished = false;
    const previousFocus = doc.activeElement;
    const resize = () => {
      width = Math.max(1, win.innerWidth); height = Math.max(1, win.innerHeight);
      ratio = Math.min(win.devicePixelRatio || 1, 1.75);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      overlay.style.setProperty("--arc-focus-x", `${width * (height < 540 && width >= 600 ? .29 : .5)}px`);
      overlay.style.setProperty("--arc-focus-y", `${height * (height < 540 && width >= 600 ? .49 : .43)}px`);
      if (raf === null && !finished) draw(frameAt(elapsed));
    };
    const markSeen = () => { if (!preview) { try { storage.setItem(SEEN_KEY, 'seen'); } catch (_) {} } };
    const finish = () => {
      if (finished) return;
      finished = true;
      if (raf !== null) win.cancelAnimationFrame(raf);
      win.clearTimeout(slowTimer);
      observer.disconnect();
      win.removeEventListener('resize', resize);
      win.removeEventListener('flutter-first-frame', onReady);
      win.removeEventListener('arc-skip-intro', onSkip);
      doc.removeEventListener('visibilitychange', onVisibility);
      doc.removeEventListener('keydown', onKey);
      media.removeEventListener('change', onMotion);
      for (const [element, inert] of blocked) element.inert = inert;
      blocked.clear();
      delete html.dataset.arcIntro;
      const restoreFocus = doc.activeElement === overlay || doc.activeElement === skip || doc.activeElement === retry;
      overlay.remove();
      if (restoreFocus && previousFocus && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
      markSeen();
    };
    const schedule = () => { if (raf === null && !finished && !doc.hidden) raf = win.requestAnimationFrame(tick); };
    const beginReveal = () => {
      if (!ready || opening !== null || finished) return;
      if (media.matches) { finish(); return; }
      opening = 0;
      last = null;
      html.dataset.arcIntro = 'opening';
      status.textContent = 'Welcome to your next chapter';
      schedule();
    };
    const onReady = () => { ready = true; if (elapsed >= LENGTH) beginReveal(); };
    // Skipping must release the page even if Flutter's first-frame event is late
    // or was missed during a development restart. It must not depend on RAF.
    const onSkip = () => finish();
    const onKey = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); onSkip(); }
      if (event.key === 'Tab') {
        const controls = overlay.hasAttribute('data-slow') ? [skip, retry] : [skip];
        const index = controls.indexOf(doc.activeElement);
        event.preventDefault(); controls[(index + (event.shiftKey ? controls.length - 1 : 1)) % controls.length].focus();
      }
    };
    const onMotion = () => { if (media.matches) finish(); };
    const onVisibility = () => {
      last = null;
      if (doc.hidden && raf !== null) { win.cancelAnimationFrame(raf); raf = null; }
      else schedule();
    };
    skip.addEventListener('click', onSkip);
    retry.addEventListener('click', () => win.location.reload());
    win.addEventListener('resize', resize);
    win.addEventListener('flutter-first-frame', onReady);
    win.addEventListener('arc-skip-intro', onSkip);
    doc.addEventListener('keydown', onKey);
    doc.addEventListener('visibilitychange', onVisibility);
    media.addEventListener('change', onMotion);
    const slowTimer = win.setTimeout(() => {
      if (!ready && !finished) finish();
    }, 15000);

    function glow(x, y, radius, color, alpha) {
      const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
      gradient.addColorStop(0, `rgba(${color},${alpha})`);
      gradient.addColorStop(.32, `rgba(${color},${alpha * .42})`);
      gradient.addColorStop(1, `rgba(${color},0)`);
      ctx.fillStyle = gradient; ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill();
    }
    function sphere(point, radius, color, opacity) {
      const r = radius * point.perspective;
      ctx.save(); ctx.globalAlpha = opacity;
      glow(point.x, point.y, r * 3.5, color === 'lime' ? '161,210,106' : '169,141,240', .19);
      const gradient = ctx.createRadialGradient(point.x - r * .35, point.y - r * .48, r * .05, point.x + r * .14, point.y + r * .15, r * 1.22);
      const colors = color === 'lime' ? ['#f3ffdb', '#d1ee9e', '#8ba85c', '#21321d'] : ['#f1eaff', '#c8b5f1', '#80679f', '#272134'];
      colors.forEach((c, i) => gradient.addColorStop([0, .33, .72, 1][i], c));
      ctx.fillStyle = gradient; ctx.beginPath(); ctx.arc(point.x, point.y, r, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = color === 'lime' ? 'rgba(230,255,190,.33)' : 'rgba(232,217,255,.35)';
      ctx.lineWidth = .65; ctx.stroke();
      const shine = ctx.createRadialGradient(point.x - r * .36, point.y - r * .5, 0, point.x - r * .36, point.y - r * .5, r * .7);
      shine.addColorStop(0, 'rgba(255,255,255,.2)'); shine.addColorStop(1, 'rgba(255,255,255,0)');
      ctx.fillStyle = shine; ctx.fill(); ctx.restore();
    }
    function ring(index, state, scale, center, front) {
      const tilt = [1.12, -.99, .66][index];
      const turn = [.32, 1.56, 2.53][index] + state.t * .13;
      const color = ['189,219,157', '190,172,229', '211,223,202'][index];
      for (let i = 0; i < 100; i++) {
        const a = i / 100 * Math.PI * 2;
        const b = (i + 1) / 100 * Math.PI * 2;
        const p = project([Math.cos(a), Math.sin(a), 0], tilt, turn, scale, center);
        const q = project([Math.cos(b), Math.sin(b), 0], tilt, turn, scale, center);
        if ((p.z >= 0) !== front) continue;
        ctx.strokeStyle = `rgba(${color},${state.ringAlpha * (front ? .36 : .12)})`;
        ctx.lineWidth = front ? .85 : .65;
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke();
      }
    }
    function orbitPoint(state, side, scale, center) {
      const angle = state.angle + side * Math.PI;
      return project([Math.cos(angle) * state.distance, Math.sin(angle) * state.distance, 0], 1.04, -.25,
        scale, center);
    }
    function draw(state) {
      overlay.dataset.stage = state.t < .3 ? "approach" : state.t < .72 ? "orbit" : "connection";
      ctx.fillStyle = '#070908'; ctx.fillRect(0, 0, width, height);
      const scale = Math.min(width * .265, height * .245, 210);
      const split = height < 540 && width >= 600;
      const center = { x: width * (split ? .29 : .5), y: height * (split ? .49 : .43) };
      glow(center.x - scale * .65, center.y, scale * 2.5, '91,129,54', .095 * state.appear);
      glow(center.x + scale * .85, center.y - scale * .18, scale * 2, '111,85,145', .07 * state.appear);
      // Deterministic dust; no noisy per-frame random generation.
      for (let i = 0; i < 54; i++) {
        const x = ((i * 331.7 + 71) % 997) / 997 * width;
        const y = ((i * 181.3 + 113) % 727) / 727 * height;
        const alpha = (.07 + (i % 4) * .025) * state.appear;
        ctx.fillStyle = `rgba(198,215,186,${alpha})`;
        ctx.beginPath(); ctx.arc(x, y + Math.sin(state.t * 2 + i) * 2, i % 7 === 0 ? 1 : .55, 0, Math.PI * 2); ctx.fill();
      }
      for (let i = 0; i < 3; i++) ring(i, state, scale, center, false);
      const bodies = [0, 1].map(side => ({ side, point: orbitPoint(state, side, scale, center) }));
      bodies.sort((a, b) => a.point.z - b.point.z);
      for (const body of bodies) {
        if (body.point.z >= 0) continue;
        sphere(body.point, scale * (body.side ? .155 : .192), body.side ? 'lilac' : 'lime', state.appear * (1 - state.joined));
      }
      glow(center.x, center.y, scale * .9, '183,220,135', state.core * .17);
      if (state.core > .001) sphere({ ...center, z: 0, perspective: 1 }, scale * .19, 'lime', state.core);
      for (let i = 0; i < 3; i++) ring(i, state, scale, center, true);
      for (const body of bodies) {
        if (body.point.z < 0) continue;
        sphere(body.point, scale * (body.side ? .155 : .192), body.side ? 'lilac' : 'lime', state.appear * (1 - state.joined));
      }
      if (state.core > 0) {
        const satellite = project([.83, .54, 0], 1.12, .32, scale, center);
        sphere(satellite, scale * .027, 'lilac', state.core);
        const second = project([-.71, -.7, 0], -.99, 1.56, scale, center);
        ctx.globalAlpha = state.core * .7; ctx.fillStyle = '#eef6df';
        ctx.beginPath(); ctx.arc(second.x, second.y, scale * .018, 0, Math.PI * 2); ctx.fill(); ctx.globalAlpha = 1;
      }
    }
    function tick(now) {
      raf = null;
      const delta = last === null ? 0 : Math.max(0, now - last); last = now;
      if (opening !== null) {
        opening += delta;
        const fraction = clamp(opening / REVEAL);
        const radius = Math.hypot(width, height) * Math.pow(fraction, 1.65);
        overlay.style.setProperty('--arc-aperture', `${radius.toFixed(1)}px`);
        if (fraction >= 1) { finish(); return; }
      } else {
        elapsed = Math.min(LENGTH, elapsed + delta);
        draw(frameAt(elapsed));
        progress.style.transform = `scaleX(${elapsed / LENGTH})`;
        if (elapsed >= LENGTH) {
          status.textContent = ready ? 'Welcome to your next chapter' : 'Opening your workspace';
          if (ready) beginReveal();
          else { last = null; return; }
        }
      }
      schedule();
    }
    resize();
    overlay.focus({ preventScroll: true });
    schedule();
    return { finish, onReady, onSkip };
  }
  return { project, frameAt, shouldPlay, mount, SEEN_KEY, LENGTH, REVEAL };
});
