import test from 'node:test';
import assert from 'node:assert/strict';

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
          return createJsonResponse(201, { ok: true });
        },
      }),
  });

  assert.equal(exitCode, 2);
  assert.equal(calls, 0);
  assert.match(io.err.join('\n'), /option `--width <width>` value is invalid/i);
});

test('sandbox create rejects unknown options', async () => {
  const io = createIo();
  const exitCode = await runCli({
    argv: ['sandbox', 'create', '--bogus', '1', '--json'],
    io,
    clientFactory: (options) => new VergeClient({ ...options, token: 'token', fetchImpl: async () => createJsonResponse(200, []) }),
  });

  assert.equal(exitCode, 2);
  assert.match(io.err.join('\n'), /unknown option `--bogus`/i);
});

test('missing global option value reports the actual parsing problem', async () => {
  const io = createIo();
  const exitCode = await runCli({
    argv: ['--token', 'sandbox', 'list', '--json'],
    io,
    clientFactory: (options) => new VergeClient({ ...options, token: 'token', fetchImpl: async () => createJsonResponse(200, []) }),
  });

  assert.equal(exitCode, 2);
  assert.match(io.err.join('\n'), /option `--token <token>` value is missing/i);
});

test('sandbox list emits JSON on success', async () => {
  const io = createIo();
  const exitCode = await runCli({
    argv: ['sandbox', 'list', '--json'],
    io,
    clientFactory: (options) =>
      new VergeClient({
        ...options,
        token: 'token',
        fetchImpl: async () =>
          createJsonResponse(200, [
            { id: 'sbx-1', alias: 'shopping', browser: { vnc_entry_base_url: 'http://example.test/vnc/' } },
          ]),
      }),
  });

  assert.equal(exitCode, 0);
  assert.deepEqual(JSON.parse(io.out[0] ?? 'null'), [
    { id: 'sbx-1', alias: 'shopping', browser: { vnc_entry_base_url: 'http://example.test/vnc/' } },
  ]);
});
