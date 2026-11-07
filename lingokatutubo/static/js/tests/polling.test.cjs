const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const vm = require('node:vm');

function harness(fetch) {
  const timers = new Map();
  const listeners = new Map();
  let timerId = 0;
  const window = {
    setTimeout(fn, delay) { timers.set(++timerId, { fn, delay }); return timerId; },
    clearTimeout(id) { timers.delete(id); },
  };
  const document = {
    hidden: false,
    addEventListener(name, fn) { listeners.set(name, fn); },
    removeEventListener(name) { listeners.delete(name); },
  };
  vm.runInNewContext(readFileSync(resolve(__dirname, '../app.js'), 'utf8'), {
    window, document, fetch, console: { error() {} },
  });
  return { api: window.LingoKatutuboPolling, timers, listeners, document };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const response = (data, ok = true) => ({ ok, status: ok ? 200 : 503,
  headers: { get: () => 'application/json' }, json: async () => data });

test('repeated starts and manual checks do not overlap requests', async () => {
  let calls = 0, release;
  const h = harness(() => { calls++; return new Promise(resolve => { release = resolve; }); });
  const first = h.api.start('job', '/status/one', {});
  assert.equal(h.api.start('job', '/status/one', {}), first);
  first.poll(); first.poll();
  assert.equal(calls, 1);
  release(response({status: 'processing'})); await settle();
  assert.equal(first.lastData.status, 'processing');
  first.stop();
  assert.equal(h.timers.size, 0);
});

test('outage preserves last confirmed state and hides diagnostic details', async () => {
  let fail = false, message;
  const h = harness(async () => {
    if (fail) throw new Error('private database credential');
    return response({status: 'processing'});
  });
  const controller = h.api.start('job', '/status/one', {onNetworkState: value => { message = value; }});
  await settle(); fail = true; controller.poll(); await settle();
  assert.equal(controller.lastData.status, 'processing');
  assert.equal(controller.stopped, false);
  assert.match(message, /last confirmed/i);
  assert.doesNotMatch(message, /private|credential/);
});

test('malformed JSON does not leak a response fragment', async () => {
  let message;
  const h = harness(async () => ({...response({}), json: async () => { throw new SyntaxError('private stack excerpt'); }}));
  h.api.start('job', '/status/one', {onNetworkState: value => { message = value; }});
  await settle();
  assert.doesNotMatch(message, /private|stack/);
  assert.match(message, /status/i);
});

test('uncertain or unknown payload cannot become a terminal state', async () => {
  let terminal = 0;
  const h = harness(async () => response({status_uncertain: true}));
  const controller = h.api.start('job', '/status/one', {onTerminal: () => terminal++});
  await settle();
  assert.equal(terminal, 0);
  assert.equal(controller.stopped, false);
  assert.equal(controller.lastData, null);
});

test('confirmed terminal response stops polling exactly once', async () => {
  let calls = 0, terminal = 0;
  const h = harness(async () => { calls++; return response({status: 'failed'}); });
  const controller = h.api.start('job', '/status/one', {onTerminal: () => terminal++});
  await settle(); controller.poll();
  assert.equal(calls, 1); assert.equal(terminal, 1);
  assert.equal(controller.stopped, true);
  assert.equal(h.timers.size, 0);
  assert.equal(h.api.controllers.size, 0);
});

test('status checks are uncached reads and resume after first-check outage', async () => {
  let options;
  const h = harness(async (_url, value) => { options = value; throw new Error('offline'); });
  h.api.start('job', '/status/one', {}); await settle();
  assert.equal(options.cache, 'no-store');
  assert.equal(options.credentials, 'same-origin');
  assert.equal(options.method, undefined);
  h.listeners.get('visibilitychange')();
  assert.equal([...h.timers.values()][0].delay, 0);
});
