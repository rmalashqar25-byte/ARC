'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const { mount } = require('../web/arc_startup.js');

function harness() {
  const listeners = new Map();
  const status = { textContent: 'Opening your workspace…' };
  let removed = false, reloaded = false, retryClick, deadline;
  const panel = { remove() { removed = true; } };
  const retry = { hidden: true, addEventListener(_, fn) { retryClick = fn; } };
  const elements = { 'arc-startup': panel, 'arc-startup-status': status, 'arc-startup-retry': retry };
  const win = {
    document: { getElementById: id => elements[id] },
    location: { reload() { reloaded = true; } }, Event,
    addEventListener(name, fn) { listeners.set(name, fn); },
    removeEventListener(name) { listeners.delete(name); },
    dispatchEvent(event) { listeners.get(event.type)?.(event); },
    setTimeout(fn) { deadline = fn; return 1; }, clearTimeout() { deadline = null; },
  };
  const controller = mount(win);
  return { win, status, retry, listeners, controller, removed: () => removed,
    expire() { deadline?.(); }, clickRetry() { retryClick(); }, reloaded: () => reloaded };
}

test('startup remains visible until the real first frame, including after Skip intro', () => {
  const h = harness();
  h.win.dispatchEvent(new Event('arc-skip-intro'));
  assert.equal(h.removed(), false);
  h.win.dispatchEvent(new Event('flutter-first-frame'));
  assert.equal(h.removed(), true);
  assert.equal(h.listeners.size, 0);
  h.expire();
  assert.equal(h.retry.hidden, true);
});

test('a slow start offers retry without hiding startup or blocking late success', () => {
  const h = harness(); h.expire();
  assert.equal(h.retry.hidden, false);
  assert.match(h.status.textContent, /Still opening/);
  assert.equal(h.removed(), false);
  h.win.dispatchEvent(new Event('flutter-first-frame'));
  assert.equal(h.removed(), true);
});

test('loading failures expose a safe recovery message and dismiss the intro', () => {
  const h = harness(); let skipped = false;
  h.win.addEventListener('arc-skip-intro', () => { skipped = true; });
  h.controller.onError();
  assert.equal(skipped, true);
  assert.equal(h.retry.hidden, false);
  const message = h.status.textContent;
  h.controller.onProgress({ detail: 'engine' }); h.expire();
  assert.equal(h.status.textContent, message);
  assert.doesNotMatch(message, /Flutter|backend|Exception/);
  h.clickRetry(); assert.equal(h.reloaded(), true);
});

test('real loading stages update startup while it is active', () => {
  const h = harness(); h.controller.onProgress({ detail: 'engine' });
  assert.equal(h.status.textContent, 'Preparing your workspace…');
  h.controller.onReady(); h.controller.onError();
  assert.equal(h.retry.hidden, true);
});
