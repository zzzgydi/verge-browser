const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../../apps/api-server/app/static/vnc_session.html'), 'utf8');
const source = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1].replace(/import RFB from .*?;/, '');

function page({ rejectLocalWrite = false, rejectLocalRead = false, postError = null, pendingPost = false, pendingGet = false, pendingLocalWrite = false, invalidPostJson = false, expired = false } = {}) {
  const events = {};
  const remoteEvents = {};
  const elements = new Map();
  const state = { local: 'LOCAL-A', remote: 'REMOTE-A', reads: 0, requests: [], writes: [], keys: [], connected: true };
  let finishPost;
  let finishGet;
  let finishLocalWrite;
  function element(id) {
    if (!elements.has(id)) {
      const attrs = new Set(id === 'fallback' ? ['hidden'] : []);
      elements.set(id, {
        handlers: {}, disabled: false,
        textContent: '', value: '', classList: { toggle() {}, remove() {} },
        hasAttribute: name => attrs.has(name), setAttribute: name => attrs.add(name),
        removeAttribute: name => attrs.delete(name), focus() { state.focused = id; }, select() {},
        addEventListener(name, handler) { this.handlers[name] = handler; },
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
      readText: async () => {
        state.reads++;
        if (rejectLocalRead) throw new Error('Local read denied');
        return state.local;
      },
      writeText: async text => {
        if (pendingLocalWrite) await new Promise(resolve => finishLocalWrite = resolve);
        if (rejectLocalWrite) throw new Error('Local write denied');
        state.local = text;
        state.writes.push(text);
      },
    } },
    fetch: async (url, options) => {
      const method = options.method || 'GET';
      state.requests.push({ url, method });
      if (expired) return { ok: false, status: 401, json: async () => ({ code: 401, message: 'expired sandbox session' }) };
      if (method === 'POST') {
        if (pendingPost) await new Promise(resolve => finishPost = resolve);
        if (postError) return { ok: false, status: 502, json: async () => ({ status: 'error', ...postError }) };
        if (invalidPostJson) return { ok: true, json: async () => { throw new SyntaxError('Unexpected token <'); } };
        state.remote = JSON.parse(options.body).text;
        return { ok: true, json: async () => ({ status: 'ok' }) };
      }
      if (pendingGet) await new Promise(resolve => finishGet = resolve);
      return { ok: true, json: async () => ({ status: 'ok', text: state.remote }) };
    },
    RFB: class {
      focus() {}
      addEventListener(name, handler) {
        remoteEvents[name] = handler;
      }
      sendKey(...key) { if (state.connected) state.keys.push(key); }
    },
  });
  vm.runInContext(source, context);
  remoteEvents.connect();
  return { state, events, elements, run: code => vm.runInContext(code, context), finishPost: () => finishPost(),
    finishGet: () => finishGet(), finishLocalWrite: () => finishLocalWrite(),
    click: id => { if (!element(id).disabled) return element(id).handlers.click(); },
    disconnect() { state.connected = false; remoteEvents.disconnect({ detail: { clean: false } }); } };
}

async function flush() {
  for (let i = 0; i < 100; i++) await Promise.resolve();
}

test('explicit copy transfers the same remote text again without polling', async () => {
  const p = page();
  await p.click('copy-remote');
  p.state.local = 'LOCAL-B';
  await p.click('copy-remote');
  assert.equal(p.state.local, 'REMOTE-A');
  assert.equal(p.state.writes.length, 2);
  assert.equal(p.state.requests.length, 2);
});

test('denied local copy uses the fetched text without a second GET', async () => {
  const p = page({ rejectLocalWrite: true });
  await p.click('copy-remote');
  assert.equal(p.state.requests.length, 1);
  assert.equal(p.elements.get('fallback-text').value, 'REMOTE-A');
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), false);
});

test('remote write failure preserves text and is not misreported as local permission failure', async () => {
  const p = page({ postError: { code: 'clipboard_timeout', message: 'clipboard write timed out' } });
  await p.click('paste-local');
  assert.equal(p.elements.get('fallback-text').value, 'LOCAL-A');
  assert.match(p.elements.get('fallback-message').textContent, /Sending text to the sandbox failed/);
  assert.equal(p.elements.get('fallback-error').textContent, 'clipboard write timed out');
  assert.equal(p.state.keys.length, 0);
});

test('explicit local paste waits for POST before dispatching remote keys', async () => {
  const p = page({ pendingPost: true });
  const paste = p.click('paste-local');
  await flush();
  assert.equal(p.state.requests.length, 1);
  assert.equal(p.state.keys.length, 0);
  p.finishPost();
  await paste;
  assert.equal(p.state.remote, 'LOCAL-A');
  assert.deepEqual(p.state.keys, [[0xffe3, 'ControlLeft', true], [0x0076, 'KeyV'], [0xffe3, 'ControlLeft', false]]);
});

test('remote and fallback hotkeys never enter a document clipboard interceptor', () => {
  const p = page();
  p.run('showFallback({ title: "Paste", message: "", mode: "paste" })');
  for (const name of ['keydown', 'keyup', 'copy', 'cut', 'paste']) assert.equal(p.events[name], undefined);
  assert.equal(p.state.reads, 0);
  assert.equal(p.state.writes.length, 0);
  assert.equal(p.state.requests.length, 0);
});

test('disconnect during clipboard POST cannot report a successful paste', async () => {
  const p = page({ pendingPost: true });
  const paste = p.click('paste-local');
  await flush();
  p.disconnect();
  p.finishPost();
  await paste;
  assert.equal(p.state.keys.length, 0);
  assert.doesNotMatch(p.elements.get('status').textContent, /shortcut dispatched/);
  assert.equal(p.elements.get('fallback-text').value, 'LOCAL-A');
});

test('manual local text remains editable when remote write fails', async () => {
  const p = page({ postError: { code: 'clipboard_timeout', message: 'clipboard write timed out' } });
  p.run('showFallback({ title: "Paste", message: "", mode: "paste", value: "MANUAL-TEXT" })');
  await p.click('fallback-action');
  assert.equal(p.elements.get('fallback-text').value, 'MANUAL-TEXT');
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), false);
});

test('HTTP 200 with invalid JSON cannot trigger a remote paste', async () => {
  const p = page({ invalidPostJson: true });
  await p.click('paste-local');
  assert.equal(p.state.keys.length, 0);
  assert.equal(p.elements.get('fallback-text').value, 'LOCAL-A');
});

test('denied local clipboard permission only affects the explicit transfer button', async () => {
  const p = page({ rejectLocalRead: true });
  assert.equal(p.state.reads, 0);
  assert.equal(p.events.keydown, undefined);
  await p.click('paste-local');
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), false);
  assert.equal(p.state.requests.length, 0);
  assert.equal(p.state.remote, 'REMOTE-A');
});

test('expired HTTP session explains recovery without overwriting the remote clipboard', async () => {
  const p = page({ expired: true });
  await p.click('paste-local');
  assert.match(p.elements.get('fallback-error').textContent, /Open a new session URL/);
  assert.equal(p.state.remote, 'REMOTE-A');
  assert.equal(p.state.keys.length, 0);
  assert.equal(p.events.keydown, undefined);
});

test('explicit transfers retain Unicode text', async () => {
  const p = page();
  p.state.local = '\u4e2d\u6587\n\ud83d\ude80';
  await p.click('paste-local');
  assert.equal(p.state.remote, '\u4e2d\u6587\n\ud83d\ude80');
  p.state.local = '';
  await p.click('copy-remote');
  assert.equal(p.state.local, '\u4e2d\u6587\n\ud83d\ude80');
});

test('connection status remains separate from clipboard feedback', async () => {
  const p = page();
  await flush();
  assert.equal(p.elements.get('connection').textContent, 'Connected');
  await p.click('copy-remote');
  assert.equal(p.elements.get('connection').textContent, 'Connected');
  assert.match(p.elements.get('status').textContent, /Remote text copied/);
  p.disconnect();
  assert.equal(p.elements.get('connection').textContent, 'Connection lost');
  assert.equal(p.elements.get('status').textContent, '');
});

test('transfer dialog traps Tab locally and Escape returns focus to the remote screen', async () => {
  const p = page();
  p.run('showFallback({ title: "Paste", message: "", mode: "paste" })');
  await flush();
  const keydown = p.elements.get('fallback').handlers.keydown;
  let prevented = false;
  keydown({ key: 'Tab', shiftKey: true, target: p.elements.get('fallback-text'), preventDefault() { prevented = true; } });
  assert.ok(prevented);
  assert.equal(p.state.focused, 'fallback-action');
  keydown({ key: 'Tab', shiftKey: false, target: p.elements.get('fallback-action'), preventDefault() {} });
  assert.equal(p.state.focused, 'fallback-text');
  keydown({ key: 'Escape', preventDefault() {} });
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), true);
  assert.equal(p.state.focused, 'screen');
});

test('pending manual paste blocks repeat submission and dismissal until completion', async () => {
  const p = page({ pendingPost: true });
  p.run('showFallback({ title: "Paste", message: "", mode: "paste", value: "MANUAL-TEXT", actionLabel: "Paste to remote" })');
  const paste = p.click('fallback-action');
  await flush();
  assert.equal(p.elements.get('fallback-action').disabled, true);
  assert.equal(p.elements.get('fallback-action').hasAttribute('aria-busy'), true);
  assert.equal(p.elements.get('fallback-action').textContent, 'Sending...');
  assert.equal(p.elements.get('fallback-cancel').disabled, true);
  assert.equal(p.elements.get('fallback-text').readOnly, true);
  await p.click('fallback-action');
  await p.click('fallback-cancel');
  const keydown = p.elements.get('fallback').handlers.keydown;
  keydown({ key: 'Escape', preventDefault() {} });
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), false);
  for (const shiftKey of [false, true]) {
    let prevented = false;
    keydown({ key: 'Tab', shiftKey, target: p.elements.get('fallback-text'), preventDefault() { prevented = true; } });
    assert.equal(prevented, true);
    assert.equal(p.state.focused, 'fallback-text');
  }
  assert.equal(p.state.requests.length, 1);
  assert.equal(p.state.keys.length, 0);
  p.finishPost();
  await paste;
  assert.equal(p.state.keys.filter(key => key[1] === 'KeyV').length, 1);
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), true);
  assert.equal(p.elements.get('fallback-action').hasAttribute('aria-busy'), false);
  assert.equal(p.elements.get('paste-local').disabled, false);
  assert.equal(p.elements.get('copy-remote').disabled, false);
});

test('failed manual paste restores editing and retry without losing the draft', async () => {
  const p = page({ pendingPost: true, postError: { code: 'clipboard_timeout', message: 'clipboard write timed out' } });
  p.run('showFallback({ title: "Paste", message: "", mode: "paste", value: "MANUAL-TEXT", actionLabel: "Retry" })');
  const paste = p.click('fallback-action');
  await flush();
  assert.equal(p.elements.get('fallback-text').readOnly, true);
  p.finishPost();
  await paste;
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), false);
  assert.equal(p.elements.get('fallback-text').value, 'MANUAL-TEXT');
  assert.equal(p.elements.get('fallback-text').readOnly, false);
  assert.equal(p.elements.get('fallback-action').disabled, false);
  assert.equal(p.elements.get('fallback-action').textContent, 'Retry');
  assert.equal(p.elements.get('fallback-cancel').disabled, false);
  assert.equal(p.elements.get('fallback-error').textContent, 'clipboard write timed out');
  assert.equal(p.state.keys.length, 0);
  assert.equal(p.elements.get('paste-local').disabled, true);
  await p.click('fallback-cancel');
  assert.equal(p.elements.get('paste-local').disabled, false);
});

test('pending copy and its dialog prevent a competing paste or replacement of a draft', async () => {
  const p = page({ pendingGet: true, rejectLocalRead: true, rejectLocalWrite: true });
  const copy = p.click('copy-remote');
  await flush();
  assert.equal(p.elements.get('paste-local').disabled, true);
  assert.equal(p.elements.get('copy-remote').disabled, true);
  await p.click('paste-local');
  assert.equal(p.state.reads, 0);
  p.finishGet();
  await copy;
  assert.equal(p.elements.get('fallback-text').value, 'REMOTE-A');
  assert.equal(p.elements.get('paste-local').disabled, true);
  assert.equal(p.elements.get('copy-remote').disabled, true);
  await p.click('fallback-cancel');
  await p.click('paste-local');
  p.elements.get('fallback-text').value = 'MANUAL-DRAFT';
  await p.click('copy-remote');
  assert.equal(p.state.requests.length, 1);
  assert.equal(p.elements.get('fallback-text').value, 'MANUAL-DRAFT');
  assert.equal(p.elements.get('fallback-text').readOnly, false);
});

test('pending toolbar paste blocks copy and restores buttons after completion', async () => {
  const p = page({ pendingPost: true });
  const paste = p.click('paste-local');
  await flush();
  assert.equal(p.elements.get('copy-remote').disabled, true);
  await p.click('copy-remote');
  assert.equal(p.state.requests.length, 1);
  p.finishPost();
  await paste;
  assert.equal(p.elements.get('copy-remote').disabled, false);
  await p.click('copy-remote');
  assert.equal(p.state.writes.length, 1);
});

test('pending fallback copy has the same busy and dismissal rules', async () => {
  const p = page({ pendingLocalWrite: true });
  p.run('showFallback({ title: "Copy", message: "", mode: "copy", value: "REMOTE-TEXT", actionLabel: "Copy Text" })');
  const copy = p.click('fallback-action');
  await flush();
  assert.equal(p.elements.get('fallback-action').textContent, 'Copying...');
  assert.equal(p.elements.get('fallback-action').disabled, true);
  await p.click('fallback-action');
  await p.click('fallback-cancel');
  p.elements.get('fallback').handlers.keydown({ key: 'Escape', preventDefault() {} });
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), false);
  p.finishLocalWrite();
  await copy;
  assert.deepEqual(p.state.writes, ['REMOTE-TEXT']);
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), true);
});

test('failed fallback copy remains available for manual copying and dismissal', async () => {
  const p = page({ pendingLocalWrite: true, rejectLocalWrite: true });
  p.run('showFallback({ title: "Copy", message: "", mode: "copy", value: "REMOTE-TEXT", actionLabel: "Copy Text" })');
  const copy = p.click('fallback-action');
  await flush();
  p.finishLocalWrite();
  await copy;
  assert.equal(p.elements.get('fallback-text').value, 'REMOTE-TEXT');
  assert.equal(p.elements.get('fallback-text').readOnly, true);
  assert.equal(p.elements.get('fallback-action').disabled, false);
  assert.equal(p.elements.get('fallback-action').textContent, 'Copy Text');
  assert.equal(p.elements.get('fallback-error').textContent, 'Local write denied');
  await p.click('fallback-cancel');
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), true);
  assert.equal(p.elements.get('copy-remote').disabled, false);
});

test('disconnect during manual paste preserves the draft and keeps toolbar disabled', async () => {
  const p = page({ pendingPost: true });
  p.run('showFallback({ title: "Paste", message: "", mode: "paste", value: "MANUAL-TEXT", actionLabel: "Paste to remote" })');
  const paste = p.click('fallback-action');
  await flush();
  p.disconnect();
  p.finishPost();
  await paste;
  assert.equal(p.state.keys.length, 0);
  assert.equal(p.elements.get('fallback-text').value, 'MANUAL-TEXT');
  assert.equal(p.elements.get('fallback-text').readOnly, false);
  assert.match(p.elements.get('fallback-error').textContent, /disconnected/);
  await p.click('fallback-cancel');
  assert.equal(p.elements.get('fallback').hasAttribute('hidden'), true);
  assert.equal(p.elements.get('paste-local').disabled, true);
  assert.equal(p.elements.get('copy-remote').disabled, true);
});
