import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { runCli } from '../src/cli.js';
import { VergeClient } from '../src/client.js';

interface MockIo {
  stdout: { log: (message: string) => void };
  stderr: { error: (message: string) => void };
  out: string[];
  err: string[];
}

function createIo(): MockIo {
  const out: string[] = [];
  const err: string[] = [];
  return {
    stdout: { log: (message: string) => out.push(message) },
    stderr: { error: (message: string) => err.push(message) },
    out,
    err,
  };
}

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
    height: 720,
    metadata: {},
    browser: {
      web_socket_debugger_url_present: true,
      viewport: { width: 1280, height: 720 },
      window_viewport: { x: 0, y: 0, width: 1280, height: 720 },
      page_viewport: { x: 0, y: 80, width: 1280, height: 640 },
      active_window: { window_id: '1', x: 0, y: 0, title: 'Chromium' },
    },
    ...overrides,
  };
}

test('sandbox create rejects invalid width before hitting the API', async () => {
  let calls = 0;
  const io = createIo();
  const exitCode = await runCli({
    argv: ['sandbox', 'create', '--width', 'abc', '--json'],
    io,
    clientFactory: (options) =>
      new VergeClient({
        ...options,
        token: 'token',
        fetchImpl: async () => {
          calls += 1;
          return createJsonResponse(201, envelope({ ok: true }, 'sandbox created'));
        },
      }),
  });

  assert.equal(exitCode, 2);
  assert.equal(calls, 0);
  assert.match(io.err.join('\n'), /option `--width <width>` value is invalid/i);
});

test('sandbox update accepts metadata JSON', async () => {
  let requestBody = '';
  const io = createIo();
  const exitCode = await runCli({
    argv: ['sandbox', 'update', 'shopping', '--metadata', '{"owner":"agent"}', '--json'],
    io,
    clientFactory: (options) => new VergeClient({
      ...options,
      token: 'token',
      fetchImpl: async (_input, init) => {
        requestBody = String(init?.body ?? '');
        return createJsonResponse(200, envelope(sandboxResponse({ metadata: { owner: 'agent' } }), 'sandbox updated'));
      },
    }),
  });

  assert.equal(exitCode, 0);
  assert.deepEqual(JSON.parse(requestBody), { metadata: { owner: 'agent' } });
});

test('sandbox create forwards kind selection', async () => {
  let requestBody = '';
  const io = createIo();
  const exitCode = await runCli({
    argv: ['sandbox', 'create', '--kind', 'xpra', '--width', '1280', '--height', '720', '--json'],
    io,
    clientFactory: (options) => new VergeClient({
      ...options,
      token: 'token',
      fetchImpl: async (_input, init) => {
        requestBody = String(init?.body ?? '');
        return createJsonResponse(201, envelope(sandboxResponse({ kind: 'xpra' }), 'sandbox created'));
      },
    }),
  });

  assert.equal(exitCode, 0);
  assert.equal(JSON.parse(requestBody).kind, 'xpra');
});

test('browser actions reject missing payload', async () => {
  const io = createIo();
  const exitCode = await runCli({
    argv: ['browser', 'actions', 'shopping', '--json'],
    io,
    clientFactory: (options) => new VergeClient({ ...options, token: 'token', fetchImpl: async () => createJsonResponse(200, envelope({ ok: true })) }),
  });

  assert.equal(exitCode, 2);
  assert.match(io.err.join('\n'), /missing browser actions payload/i);
});

test('browser screenshot writes output file when requested', async () => {
  const io = createIo();
  const tempDir = await mkdtemp(join(tmpdir(), 'verge-browser-cli-'));
  const outputPath = join(tempDir, 'shot.png');

  try {
    const exitCode = await runCli({
      argv: ['browser', 'screenshot', 'shopping', '--output', outputPath, '--json'],
      io,
      clientFactory: (options) => new VergeClient({
        ...options,
        token: 'token',
        fetchImpl: async () => createJsonResponse(200, envelope({
          type: 'window',
          format: 'png',
          media_type: 'image/png',
          metadata: {
            width: 1,
            height: 1,
            page_viewport: { x: 0, y: 0, width: 1, height: 1 },
            window_viewport: { x: 0, y: 0, width: 1, height: 1 },
            window_id: '1',
          },
          data_base64: Buffer.from('png-bytes').toString('base64'),
        })),
      }),
    });

    assert.equal(exitCode, 0);
    assert.equal(await readFile(outputPath, 'utf8'), 'png-bytes');
    const payload = JSON.parse(io.out[0] ?? '{}') as { output?: string };
    assert.equal(payload.output, outputPath);
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});

test('files download writes binary output file', async () => {
  const io = createIo();
  const tempDir = await mkdtemp(join(tmpdir(), 'verge-browser-cli-'));
  const outputPath = join(tempDir, 'notes.txt');

  try {
    const exitCode = await runCli({
      argv: ['files', 'download', 'shopping', '/workspace/notes.txt', '--output', outputPath, '--json'],
      io,
      clientFactory: (options) => new VergeClient({
        ...options,
        token: 'token',
        fetchImpl: async () => new Response('hello', { status: 200, headers: { 'Content-Type': 'text/plain' } }),
      }),
    });

    assert.equal(exitCode, 0);
    assert.equal(await readFile(outputPath, 'utf8'), 'hello');
  } finally {
    await rm(tempDir, { recursive: true, force: true });
  }
});
