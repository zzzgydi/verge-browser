const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../../apps/api-server/app/static/vnc_session.html'), 'utf8');
const source = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1].replace(/import RFB from .*?;/, '');

function page({ rejectLocalWrite = false, postError = null, pendingPost = false, invalidPostJson = false } = {}) {
  const events = {};
  const remoteEvents = {};
  const elements = new Map();
  const state = { local: 'LOCAL-A', remote: 'REMOTE-A', requests: [], writes: [], keys: [], connected: true };
  let finishPost;
  function element(id) {
    if (!elements.has(id)) {
      const attrs = new Set(id === 'fallback' ? ['hidden'] : []);
      elements.set(id, {
        textContent: '', value: '', classList: { toggle() {}, remove() {} },
        hasAttribute: name => attrs.has(name), setAttribute: name => attrs.add(name),
        removeAttribute: name => attrs.delete(name), focus() {}, select() {}, addEventListener() {},
      });
    }
    return elements.get(id);
  }
  const context = vm.createContext({
    URL, Date, Error, Promise, console,
    document: { getElementById: element, addEventListener: (name, handler) => events[name] = handler },
    window: {
      location: { href: 'https://example.test/sandbox/test/session/vnc.html', protocol: 'https:', host: 'example.test' },
      addEventListener() {}, clearTimeout() {},
      setTimeout(handler, ms) { if (ms <= 200) queueMicrotask(handler); return 1; },
    },
    navigator: { clipboard: {
      readText: async () => state.local,
      writeText: async text => {
        if (rejectLocalWrite) throw new Error('Local write denied');
        state.local = text;
        state.writes.push(text);
      },
    } },
    fetch: async (url, options) => {
      const method = options.method || 'GET';
      state.requests.push({ url, method });
      if (method === 'POST') {
        if (postError) return { ok: false, status: 502, json: async () => ({ status: 'error', ...postError }) };
        if (invalidPostJson) return { ok: true, json: async () => { throw new SyntaxError('Unexpected token <'); } };
        state.remote = JSON.parse(options.body).text;
        if (pendingPost) await new Promise(resolve => finishPost = resolve);
        return { ok: true, json: async () => ({ status: 'ok' }) };
      }
      return { ok: true, json: async () => ({ status: 'ok', text: state.remote }) };
    },
    RFB: class {
      focus() {}
      addEventListener(name, handler) {
        remoteEvents[name] = handler;
        if (name === 'connect') queueMicrotask(handler);
      }
      sendKey(...key) { if (state.connected) state.keys.push(key); }
    },
  });
  vm.runInContext(source, context);
  return { state, events, elements, run: code => vm.runInContext(code, context), finishPost: () => finishPost(),
    disconnect() { state.connected = false; remoteEvents.disconnect({ detail: { clean: false } }); } };
}

async function flush() {
  for (let i = 0; i < 100; i++) await Promise.resolve();
}

test('same remote text refreshes a local clipboard changed outside the session', async () => {
  const p = page();
  await p.run('syncRemoteToLocal()');
  p.state.local = 'LOCAL-B';
  await p.run('syncRemoteToLocal()');
  assert.equal(p.state.local, 'REMOTE-A');
  assert.equal(p.state.writes.length, 2);
});

test('denied local copy uses the fetched text without a second GET', async () => {
  const p = page({ rejectLocalWrite: true });
  await p.run('syncRemoteToLocal()');
  assert.equal(p.state.requests.length, 1);
  assert.equal(p.elements.get('fallback-text').value, 'REMOTE-A');
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), false);
});

test('remote write failure preserves text and is not misreported as local permission failure', async () => {
  const p = page({ postError: { code: 'clipboard_timeout', message: 'clipboard write timed out' } });
  await p.run('syncLocalToRemote({ triggerPaste: true })');
  assert.equal(p.elements.get('fallback-text').value, 'LOCAL-A');
  assert.match(p.elements.get('fallback-message').textContent, /Sending text to the sandbox failed/);
  assert.equal(p.elements.get('fallback-error').textContent, 'clipboard write timed out');
  assert.equal(p.state.keys.length, 0);
});

test('Ctrl+V sends the remote shortcut only after clipboard POST finishes', async () => {
  const p = page({ pendingPost: true });
  let prevented = false;
  let stopped = false;
  p.events.keydown({ key: 'v', ctrlKey: true, metaKey: false, altKey: false,
    preventDefault() { prevented = true; }, stopPropagation() { stopped = true; } });
  await flush();
  assert.ok(prevented && stopped);
  assert.equal(p.state.requests.length, 1);
  assert.equal(p.state.keys.length, 0);
  p.finishPost();
  await flush();
  assert.equal(p.state.remote, 'LOCAL-A');
  assert.deepEqual(p.state.keys, [[0xffe3, 'ControlLeft', true], [0x0076, 'KeyV'], [0xffe3, 'ControlLeft', false]]);
});

test('manual fallback textarea keeps native clipboard hotkeys', () => {
  const p = page();
  p.run('showFallback({ title: "Paste", message: "", mode: "paste" })');
  p.events.keydown({ key: 'v', ctrlKey: true, preventDefault() { assert.fail('native paste intercepted'); } });
  assert.equal(p.state.requests.length, 0);
});

test('disconnect during clipboard POST cannot report a successful paste', async () => {
  const p = page({ pendingPost: true });
  const paste = p.run('syncLocalToRemote({ triggerPaste: true })');
  await flush();
  p.disconnect();
  p.finishPost();
  await paste;
  assert.equal(p.state.keys.length, 0);
  assert.doesNotMatch(p.elements.get('status').textContent, /pasted into sandbox/);
  assert.equal(p.elements.get('fallback-text').value, 'LOCAL-A');
});

test('native paste event preserves the text when the remote write fails', async () => {
  const p = page({ postError: { code: 'clipboard_timeout', message: 'clipboard write timed out' } });
  p.events.paste({ clipboardData: { getData: () => 'NATIVE-TEXT' }, preventDefault() {}, stopPropagation() {} });
  await flush();
  assert.equal(p.elements.get('fallback-text').value, 'NATIVE-TEXT');
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), false);
});

test('HTTP 200 with invalid JSON cannot trigger a remote paste', async () => {
  const p = page({ invalidPostJson: true });
  await p.run('syncLocalToRemote({ triggerPaste: true })');
  assert.equal(p.state.keys.length, 0);
  assert.equal(p.elements.get('fallback-text').value, 'LOCAL-A');
});
