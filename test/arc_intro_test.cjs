'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const { project, frameAt, shouldPlay, mount, SEEN_KEY, LENGTH } = require('../web/arc_intro.js');

function harness({ reduced = false, seen = false, storageBlocked = false, canvasAvailable = true, preview = false } = {}) {
  const listeners = new Map();
  const events = () => ({
    addEventListener(type, fn) { listeners.set(type, fn); },
    removeEventListener(type, fn) { if (listeners.get(type) === fn) listeners.delete(type); },
  });
  const stored = new Map(seen ? [[SEEN_KEY, 'seen']] : []);
  const css = new Map();
  let removed = false, disconnected = false, scheduled = null, deadline = null;
  const gradient = { addColorStop() {} };
  const context = new Proxy({}, { get(_, key) { return key.startsWith('create') ? () => gradient : () => {}; }, set() { return true; } });
  const overlay = { dataset: {}, focus() {}, remove() { removed = true; }, style: { setProperty: (k, v) => css.set(k, v) }, hasAttribute: () => false, setAttribute() {} };
  const skip = { ...events(), focus() {} };
  const retry = { ...events(), focus() {} };
  const app = { tagName: 'FLUTTER-VIEW', inert: false };
  const accessibilityControl = { tagName: 'FLT-SEMANTICS-PLACEHOLDER', inert: false };
  const elements = { 'arc-intro': overlay, 'arc-intro-canvas': { getContext: () => canvasAvailable ? context : null }, 'arc-intro-skip': skip, 'arc-intro-retry': retry,
    'arc-intro-progress': { style: {} }, 'arc-intro-status': { textContent: '' } };
  const doc = { ...events(), getElementById: id => elements[id], body: { children: [app, accessibilityControl] }, documentElement: { dataset: {} }, hidden: false, activeElement: { isConnected: true, focus() {} } };
  const media = { ...events(), matches: reduced };
  const win = { ...events(), document: doc, matchMedia: () => media, URLSearchParams, location: { search: preview ? '?intro=preview' : '', reload() {} },
    localStorage: { getItem(k) { if (storageBlocked) throw Error('blocked'); return stored.get(k); }, setItem(k, v) { if (storageBlocked) throw Error('blocked'); stored.set(k, v); } },
    MutationObserver: class { observe() {} disconnect() { disconnected = true; } },
    innerWidth: 390, innerHeight: 844, devicePixelRatio: 3,
    setTimeout(callback) { deadline = callback; return 1; }, clearTimeout() { deadline = null; },
    requestAnimationFrame(fn) { scheduled = fn; return 1; }, cancelAnimationFrame() { scheduled = null; } };
  let time = 0;
  function advance(ms) {
    const end = time + ms;
    while (time <= end && scheduled) { const callback = scheduled; scheduled = null; callback(time); time += 20; }
    time = Math.max(time, end);
  }
  return { win, doc, app, accessibilityControl, stored, listeners, advance,
    expireDeadline() { if (deadline) deadline(); },
    isRemoved: () => removed, isDisconnected: () => disconnected };
}

test('the two spheres converge and leave one finished logo', () => {
  assert.equal(frameAt(0).distance, 1.34);
  assert.ok(frameAt(1800).distance < frameAt(1000).distance);
  assert.equal(frameAt(LENGTH).distance, 0);
  assert.equal(frameAt(LENGTH).core, 1);
  for (let time = 0; time < LENGTH; time += 41) {
    for (const value of Object.values(frameAt(time))) assert.ok(Number.isFinite(value));
    const point = project([Math.cos(time), Math.sin(time), 0], 1.1, .4, 200, { x: 300, y: 250 });
    assert.ok(Number.isFinite(point.x) && Number.isFinite(point.y) && point.perspective > 0);
  }
});

test('returning visitors and reduced-motion users enter directly', () => {
  for (const options of [{ seen: true }, { reduced: true }]) {
    const h = harness(options); mount(h.win);
    assert.equal(h.isRemoved(), true); assert.equal(h.app.inert, false);
    assert.equal(h.listeners.has('flutter-first-frame'), false);
  }
});

test('first visit waits for the real first frame and releases the app after reveal', () => {
  const h = harness(); const controller = mount(h.win);
  assert.equal(h.app.inert, true);
  assert.equal(h.accessibilityControl.inert, true);
  h.advance(4500); assert.equal(h.isRemoved(), false);
  assert.notEqual(h.stored.get(SEEN_KEY), 'seen');
  controller.onReady(); h.advance(1100);
  assert.equal(h.isRemoved(), true); assert.equal(h.app.inert, false);
  assert.equal(h.stored.get(SEEN_KEY), 'seen'); assert.equal(h.isDisconnected(), true);
  assert.equal(h.accessibilityControl.inert, false);
  assert.equal(h.listeners.has('keydown'), false);
});

test('skip exits without waiting for the cinematic sequence', () => {
  const h = harness(); const controller = mount(h.win);
  controller.onReady(); controller.onSkip(); h.advance(1100);
  assert.equal(h.isRemoved(), true); assert.equal(h.app.inert, false);
});

test('skip immediately releases the workspace before Flutter reports readiness', () => {
  const h = harness(); const controller = mount(h.win);
  h.advance(4000);
  controller.onSkip();
  assert.equal(h.isRemoved(), true);
  assert.equal(h.app.inert, false);
  assert.equal(h.accessibilityControl.inert, false);
  assert.equal(h.doc.documentElement.dataset.arcIntro, undefined);
  assert.equal(h.listeners.has('flutter-first-frame'), false);
  assert.equal(h.stored.get(SEEN_KEY), 'seen');
  controller.onReady(); controller.onSkip(); h.advance(1000);
  assert.equal(h.doc.documentElement.dataset.arcIntro, undefined);
});

test('Escape skips even when the tab cannot run animation frames', () => {
  const h = harness(); mount(h.win);
  h.doc.hidden = true; h.listeners.get('visibilitychange')();
  let prevented = false;
  h.listeners.get('keydown')({key: 'Escape', preventDefault() { prevented = true; }});
  assert.equal(prevented, true);
  assert.equal(h.isRemoved(), true);
  assert.equal(h.app.inert, false);
});

test('a startup failure dismisses the intro so recovery controls are usable', () => {
  const h = harness(); mount(h.win);
  h.listeners.get('arc-skip-intro')();
  assert.equal(h.isRemoved(), true);
  assert.equal(h.app.inert, false);
  assert.equal(h.listeners.has('arc-skip-intro'), false);
});

test('a missing readiness event cannot leave the introduction blocking the page forever', () => {
  const h = harness(); mount(h.win);
  h.advance(4000); h.expireDeadline();
  assert.equal(h.isRemoved(), true);
  assert.equal(h.app.inert, false);
  assert.equal(h.isDisconnected(), true);
});

test('blocked storage and unavailable graphics never prevent app entry', () => {
  const h = harness({ storageBlocked: true }); const controller = mount(h.win);
  controller.onReady(); controller.onSkip(); h.advance(1100);
  assert.equal(h.isRemoved(), true);
  const noCanvas = harness({ canvasAvailable: false }); mount(noCanvas.win);
  assert.equal(noCanvas.isRemoved(), true); assert.equal(noCanvas.app.inert, false);
  assert.equal(shouldPlay(null, false, false), true);
});

test('switching reduced motion on during the animation immediately releases focus', () => {
  const h = harness(); mount(h.win);
  h.win.matchMedia().matches = true; h.listeners.get('change')();
  assert.equal(h.isRemoved(), true); assert.equal(h.app.inert, false);
});


test('replay does not consume the first-visit experience', () => {
  const h = harness({ preview: true }); const controller = mount(h.win);
  controller.onReady(); controller.onSkip(); h.advance(1100);
  assert.equal(h.isRemoved(), true);
  assert.equal(h.stored.has(SEEN_KEY), false);
});
