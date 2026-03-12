import test from 'node:test';
import assert from 'node:assert/strict';

import { VergeClient, type FetchLike } from '../src/client.js';
import { VergeValidationError } from '../src/errors.js';

function createJsonResponse(status: number, body?: unknown): Response {
  const init: ResponseInit = { status };
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
  }
  return new Response(body === undefined ? null : JSON.stringify(body), init);
}

function envelope<T>(data: T, message = 'ok') {
  return { code: 0, message, data };
}

function sandboxResponse(overrides: Record<string, unknown> = {}) {
  return {
    id: 'sbx-1',
    alias: 'shopping',
    kind: 'xvfb_vnc',
    status: 'RUNNING',
    created_at: '2026-03-12T00:00:00Z',
    updated_at: '2026-03-12T00:00:00Z',
    last_active_at: '2026-03-12T00:00:00Z',
    width: 1280,
    height: 1024,
    metadata: {},
    browser: {
      web_socket_debugger_url_present: true,
      viewport: { width: 1280, height: 1024 },
      window_viewport: { x: 0, y: 0, width: 1280, height: 1024 },
      page_viewport: { x: 0, y: 80, width: 1280, height: 944 },
      active_window: { window_id: '1', x: 0, y: 0, title: 'Chromium' },
    },
    ...overrides,
  };
}

test('createSandbox sends metadata and optional fields', async () => {
  let requestBody = '';
  const client = new VergeClient({
    token: 'token',
    fetchImpl: async (_input, init) => {
      requestBody = String(init?.body ?? '');
      return createJsonResponse(201, envelope(sandboxResponse({ metadata: { owner: 'agent' } }), 'sandbox created'));
    },
  });

  await client.createSandbox({ metadata: { owner: 'agent' }, default_url: 'https://example.com' });
  assert.deepEqual(JSON.parse(requestBody), {
    kind: 'xvfb_vnc',
    metadata: { owner: 'agent' },
    default_url: 'https://example.com',
  });
});

test('createSandbox allows xpra kind override', async () => {
  let requestBody = '';
  const client = new VergeClient({
    token: 'token',
    fetchImpl: async (_input, init) => {
      requestBody = String(init?.body ?? '');
      return createJsonResponse(201, envelope(sandboxResponse({ kind: 'xpra' }), 'sandbox created'));
    },
  });

  await client.createSandbox({ kind: 'xpra' });
  assert.equal(JSON.parse(requestBody).kind, 'xpra');
});

test('downloadFile returns binary payload and content type', async () => {
  const client = new VergeClient({
    token: 'token',
    fetchImpl: async () => new Response(new Uint8Array([1, 2, 3]), { status: 200, headers: { 'Content-Type': 'application/octet-stream' } }),
  });

  const result = await client.downloadFile('sbx-1', '/workspace/file.bin');
  assert.equal(result.path, '/workspace/file.bin');
  assert.equal(result.contentType, 'application/octet-stream');
  assert.deepEqual(Array.from(result.data), [1, 2, 3]);
});

test('uploadFile uses multipart form data', async () => {
  let capturedBody: BodyInit | null | undefined;
  const client = new VergeClient({
    token: 'token',
    fetchImpl: async (_input, init) => {
      capturedBody = init?.body;
      return createJsonResponse(200, envelope({ path: '/workspace/uploads/file.txt' }, 'file uploaded'));
    },
  });

  await client.uploadFile('sbx-1', { filename: 'file.txt', data: new Uint8Array([104, 105]) });
  assert.ok(capturedBody instanceof FormData);
  const part = capturedBody.get('upload');
  assert.ok(part && typeof part === 'object');
  assert.equal((part as { name?: string }).name, 'file.txt');
});

test('413 responses map to VergeValidationError', async () => {
  const client = new VergeClient({
    token: 'token',
    fetchImpl: async () => createJsonResponse(413, { code: 413, message: 'upload too large', data: null }),
  });

  await assert.rejects(() => client.uploadFile('sbx-1', { filename: 'file.bin', data: new Uint8Array([1]) }), VergeValidationError);
});

test('listFiles includes query path', async () => {
  let requestedUrl = '';
  const fetchImpl: FetchLike = async (input) => {
    requestedUrl = input;
    return createJsonResponse(200, envelope([]));
  };
  const client = new VergeClient({ token: 'token', baseUrl: 'http://127.0.0.1:8000', fetchImpl });

  await client.listFiles('shopping', '/workspace/downloads');
  assert.equal(requestedUrl, 'http://127.0.0.1:8000/sandbox/shopping/files/list?path=%2Fworkspace%2Fdownloads');
});
