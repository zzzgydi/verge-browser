import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { AttachedBrowser } from '../src/browser.js';
import { connectionConfig } from '../src/config.js';
import { fixture } from './fixture.js';


const signal = () => new AbortController().signal;

test('configuration rejects unsafe endpoints and invalid bounds', () => {
  for (const baseUrl of ['file:///tmp/a', 'http://a/?secret=x', 'https://user:pass@a', 'http://a/#x']) {
    assert.equal(connectionConfig.safeParse({ baseUrl, token: 'x', sandbox: 'a' }).success, false);
  }
  assert.equal(connectionConfig.safeParse({ baseUrl: 'http://a', token: '', sandbox: 'a' }).success, false);
});

test('Camoufox discovery is read-only and tools bind stable sandbox ID', async () => {
  const f = await fixture(); const browser = new AttachedBrowser(f.config);
  try {
    await browser.initialize();
    assert.deepEqual(f.calls.map(c => c.method), ['GET']);
    assert(browser.tools().some(t => t.name === 'verge_click'));
    assert(!browser.tools().some(t => t.name.startsWith('browser_')));
    const result = await browser.call('verge_click', { ref: '@e1' }, signal());
    assert(!result.isError); assert.equal(f.calls.at(-1)?.path, '/sandbox/stable-id/browser/command');
    assert.equal(f.calls.at(-1)?.body.action, 'click');
    assert(!f.calls.some(c => c.path.includes('/cdp/')));
  } finally { await browser.close(); await f.close(); }
});

test('Chromium discovery uses pinned upstream tools without CDP or launch', async () => {
  const f = await fixture('chromium'); const browser = new AttachedBrowser(f.config);
  try {
    await browser.initialize();
    assert(browser.tools().some(t => t.name === 'browser_snapshot'));
    assert(!browser.tools().some(t => ['browser_close', 'browser_install', 'browser_run_code', 'browser_file_upload'].includes(t.name)));
    assert.deepEqual(f.calls.map(c => c.method), ['GET']);
    assert((await browser.call('browser_tabs', { action: 'close', index: 0 }, signal())).isError);
    assert((await browser.call('browser_snapshot', { filename: '/tmp/snapshot.md' }, signal())).isError);
    assert.equal((await browser.call('verge_status', {}, signal())).structuredContent?.automation, 'automation');
    assert(!f.calls.some(c => c.path.includes('/cdp/')));
  } finally { await browser.close(); await f.close(); }
});

test('handoff blocks commands and file writes until explicit resume', async () => {
  const f = await fixture(); const browser = new AttachedBrowser(f.config);
  try {
    await browser.initialize();
    assert(!(await browser.call('verge_handoff', {}, signal())).isError);
    const before = f.calls.length;
    assert((await browser.call('verge_click', { ref: '@e1' }, signal())).isError);
    assert((await browser.call('verge_file_write', { path: '/workspace/a', content: 'x' }, signal())).isError);
    assert.equal(f.calls.length, before);
    assert(!(await browser.call('verge_status', {}, signal())).isError);
    assert(!(await browser.call('verge_resume', {}, signal())).isError);
    assert(!(await browser.call('verge_snapshot', {}, signal())).isError);
    assert.equal(f.calls.filter(c => c.path.includes('session/apply')).length, 1);
  } finally { await browser.close(); await f.close(); }
});

test('arguments, workspace paths, text bounds, status, and secret fields stay constrained', async () => {
  const f = await fixture(); const browser = new AttachedBrowser(f.config);
  try {
    await browser.initialize();
    for (const [name, args] of [
      ['verge_click', {}], ['verge_click', { ref: '@e1', sandbox: 'other' }],
      ['verge_file_read', { path: '/workspace/../../etc/passwd' }],
      ['verge_file_write', { path: '/workspace/a', content: 'x'.repeat(65537) }],
      ['verge_unknown', {}],
    ] as const) assert((await browser.call(name, args, signal())).isError);
    const result = await browser.call('verge_file_write', { path: '/workspace/a', content: 'x' }, signal());
    assert.deepEqual(result.structuredContent, { path: '/workspace/a' });
    assert(!JSON.stringify(result).includes('/host/'));
    assert.equal(f.calls.at(-1)?.body.overwrite, false);
    const listing = await browser.call('verge_files_list', {}, signal());
    assert(!JSON.stringify(listing).includes('/host/'));
    assert(JSON.stringify(listing).includes('/workspace/note'));
    const shot = await browser.call('verge_screenshot', {}, signal());
    assert.equal(shot.content[1].type, 'image');
    f.setState('DEGRADED');
    assert((await browser.call('verge_click', { ref: '@e1' }, signal())).isError);
  } finally { await browser.close(); await f.close(); }
});

test('cancellation prevents queued mutation and blocks retry until explicit resume', async () => {
  const f = await fixture(); const browser = new AttachedBrowser(f.config);
  try {
    await browser.initialize(); f.setDelay(200);
    const controller = new AbortController();
    const first = browser.call('verge_click', { ref: '@e1' }, controller.signal);
    await new Promise(r => setTimeout(r, 30)); controller.abort();
    assert((await first).isError);
    assert((await browser.call('verge_click', { ref: '@e1' }, signal())).isError);
    assert.equal(f.calls.filter(c => c.path.includes('/browser/command')).length, 1);
  } finally { await browser.close(); await f.close(); }
});

test('unknown engine and unavailable credentials fail startup', async () => {
  const f = await fixture('unknown');
  try {
    await assert.rejects(new AttachedBrowser(f.config).initialize(), /browser_engine/);
    await assert.rejects(new AttachedBrowser({ ...f.config, token: 'wrong' }).initialize(), /denied/);
  } finally { await f.close(); }
});

test('request timeout blocks Camoufox mutation even before the tool deadline', async () => {
  const f = await fixture(); const browser = new AttachedBrowser({ ...f.config, requestTimeoutMs: 100 });
  try {
    await browser.initialize(); f.setDelay(400);
    assert((await browser.call('verge_click', { ref: '@e1' }, signal())).isError);
    assert.equal((await browser.call('verge_status', {}, signal())).structuredContent?.automation, 'interrupted');
    assert((await browser.call('verge_click', { ref: '@e1' }, signal())).isError);
    assert.equal(f.calls.filter(c => c.path.includes('/browser/command')).length, 1);
  } finally { await browser.close(); await f.close(); }
});

test('read-only cancellation does not interrupt automation', async () => {
  const f = await fixture(); const browser = new AttachedBrowser(f.config);
  try {
    await browser.initialize(); f.setDelay(200);
    const controller = new AbortController();
    const read = browser.call('verge_snapshot', {}, controller.signal);
    await new Promise(r => setTimeout(r, 30)); controller.abort();
    assert((await read).isError);
    assert.equal((await browser.call('verge_status', {}, signal())).structuredContent?.automation, 'automation');
  } finally { await browser.close(); await f.close(); }
});

test('disconnect attempts every handle and reports cleanup failure without stale handles', async () => {
  const f = await fixture(); const browser = new AttachedBrowser(f.config);
  const closed: string[] = [];
  try {
    await browser.initialize();
    Object.assign(browser, {
      mcp: { close: async () => { closed.push('mcp'); throw Error('transport closed'); } },
      upstream: { close: async () => { closed.push('upstream'); } },
      browser: { close: async () => { closed.push('browser'); } },
    });
    const result = await browser.call('verge_handoff', {}, signal());
    assert(result.isError); assert(JSON.stringify(result).includes('transport closed'));
    assert.deepEqual(closed, ['mcp', 'upstream', 'browser']);
    assert.equal((await browser.call('verge_status', {}, signal())).structuredContent?.automation, 'handoff');
    assert(!(await browser.call('verge_resume', {}, signal())).isError);
    assert.equal(closed.length, 3);
  } finally { await browser.close(); await f.close(); }
});

test('HTTPS connection refuses a plaintext CDP endpoint before connecting', async () => {
  const config = connectionConfig.parse({ baseUrl: 'https://verge.example', token: 'test-token', sandbox: 'a' });
  const browser = new AttachedBrowser(config);
  Object.assign(browser, { sandbox: {id:'a'}, client: () => ({ getCdpInfo: async () => ({cdp_url:'ws://verge.example/cdp?ticket=secret'}) }) });
  await assert.rejects((browser as any).connect(signal()), /without downgrading HTTPS/);
  await browser.close();
});

test('upstream MCP error results redact configured secrets and ticket URLs', async () => {
  const f = await fixture('chromium'); const browser = new AttachedBrowser(f.config);
  try {
    await browser.initialize();
    Object.assign(browser, {
      browser: { isConnected: () => true, close: async () => {} },
      mcp: { close: async () => {}, callTool: async () => ({ isError: true, content: [{type:'text',text:'test-token ws://localhost/cdp?ticket=secret'}] }) },
    });
    const result = await browser.call('browser_snapshot', {}, signal());
    assert(result.isError);
    assert(!JSON.stringify(result).includes('test-token'));
    assert(!JSON.stringify(result).includes('ticket=secret'));
    assert.equal((await browser.call('verge_status', {}, signal())).structuredContent?.automation, 'interrupted');
  } finally { await browser.close(); await f.close(); }
});

test('built stdio artifact discovers and calls tools without source imports', async () => {
  const f = await fixture();
  const transport = new StdioClientTransport({ command: process.execPath,
    args: ['dist/bridge.js'], env: { ...process.env as Record<string, string>, VERGE_DSH_CONFIG: JSON.stringify(f.config) }, stderr: 'pipe' });
  const client = new Client({ name: 'test', version: '1' });
  try {
    await client.connect(transport);
    assert((await client.listTools()).tools.some(t => t.name === 'verge_snapshot'));
    const result = await client.callTool({ name: 'verge_snapshot', arguments: {} });
    assert(!result.isError);
    assert.equal((result.structuredContent as any).action, 'snapshot');
  } finally { await client.close(); await f.close(); }
});
