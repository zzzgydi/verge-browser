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

function sandboxResponse(overrides: Record<string, unknown> = {}) {
  return {
    id: 'sbx-1',
    alias: 'shopping',
    status: 'RUNNING',
    created_at: '2026-03-12T00:00:00Z',
    updated_at: '2026-03-12T00:00:00Z',
    last_active_at: '2026-03-12T00:00:00Z',
    width: 1280,
    height: 1024,
    metadata: {},
    browser: {
      cdp_url: 'ws://x',
      vnc_entry_base_url: 'http://x',
      vnc_ticket_endpoint: 'http://x/tickets',
      viewport: { width: 1280, height: 1024 },
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
      return createJsonResponse(201, sandboxResponse({ metadata: { owner: 'agent' } }));
    },
  });

  await client.createSandbox({ metadata: { owner: 'agent' }, default_url: 'https://example.com' });
  assert.deepEqual(JSON.parse(requestBody), {
    metadata: { owner: 'agent' },
    default_url: 'https://example.com',
  });
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
      return createJsonResponse(200, { path: '/workspace/uploads/file.txt' });
    },
  });

  await client.uploadFile('sbx-1', { filename: 'file.txt', data: new Uint8Array([104, 105]) });
  assert.ok(capturedBody instanceof FormData);
  const part = capturedBody.get('upload');
  assert.ok(part instanceof File);
  assert.equal(part.name, 'file.txt');
});

test('413 responses map to VergeValidationError', async () => {
  const client = new VergeClient({
    token: 'token',
    fetchImpl: async () => createJsonResponse(413, { detail: 'upload too large' }),
  });

  await assert.rejects(() => client.uploadFile('sbx-1', { filename: 'file.bin', data: new Uint8Array([1]) }), VergeValidationError);
});

test('listFiles includes query path', async () => {
  let requestedUrl = '';
  const fetchImpl: FetchLike = async (input) => {
    requestedUrl = input;
    return createJsonResponse(200, []);
  };
  const client = new VergeClient({ token: 'token', baseUrl: 'http://127.0.0.1:8000', fetchImpl });

  await client.listFiles('shopping', '/workspace/downloads');
  assert.equal(requestedUrl, 'http://127.0.0.1:8000/sandboxes/shopping/files/list?path=%2Fworkspace%2Fdownloads');
});
