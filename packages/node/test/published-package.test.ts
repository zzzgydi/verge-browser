import test from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const script = new URL('../../scripts/verify-published-package.mjs', import.meta.url).href;

for (const [label, responses, expectedCalls, success, summaryMode = 'present'] of [
  ['immediate match', [200], 1, true],
  ['registry propagation', [404, 404, 200], 3, true],
  ['transient failures', ['network', 'timeout', 429, 500, 503, 200], 6, true],
  ['response body timeout', ['body-timeout', 200], 2, true],
  ['missing version exhausted', [404], 6, false],
  ['network exhausted', ['network'], 6, false],
  ['server errors exhausted', [503], 6, false],
  ['authentication error', [401], 1, false],
  ['access denied', [403], 1, false],
  ['integrity mismatch', ['mismatch'], 1, false],
  ['malformed response', ['malformed'], 1, false],
  ['missing summary variable', [200], 1, true, 'missing'],
  ['empty summary variable', [200], 1, true, 'empty'],
  ['integrity mismatch without summary', ['mismatch'], 1, false, 'missing'],
] as const) {
  test(`published package check: ${label}`, () => {
    const directory = mkdtempSync(join(tmpdir(), 'verge-registry-test-'));
    const summary = join(directory, 'summary.md');
    writeFileSync(join(directory, 'package-metadata.json'), JSON.stringify({
      name: 'verge-browser', version: '0.4.0', integrity: 'expected-integrity',
    }));
    try {
      const env: NodeJS.ProcessEnv = { ...process.env, PACKAGE_DIR: directory, GITHUB_STEP_SUMMARY: summary };
      if (summaryMode === 'missing') delete env.GITHUB_STEP_SUMMARY;
      if (summaryMode === 'empty') env.GITHUB_STEP_SUMMARY = '';
      const result = spawnSync(process.execPath, ['--input-type=module', '-e', `
        import assert from 'node:assert/strict';
        const responses = ${JSON.stringify(responses)};
        let calls = 0;
        let delays = 0;
        const timeout = AbortSignal.timeout;
        AbortSignal.timeout = ms => { assert.equal(ms, 10000); return timeout(ms); };
        globalThis.setTimeout = (callback, ms) => {
          assert.equal(ms, 10000); delays++; callback();
        };
        globalThis.fetch = async (url, options) => {
          assert.ok(url.startsWith('https://registry.npmjs.org/verge-browser/0.4.0?write=true&t='));
          assert.ok(options.signal instanceof AbortSignal);
          const status = responses[Math.min(calls++, responses.length - 1)];
          if (status === 'network') throw new TypeError('fetch failed');
          if (status === 'timeout') throw new DOMException('timed out', 'TimeoutError');
          if (status === 'body-timeout') return { ok: true, json: async () => { throw new DOMException('timed out', 'TimeoutError'); } };
          if (status === 'malformed') return new Response('invalid JSON');
          return new Response(JSON.stringify({ dist: { integrity: status === 'mismatch' ? 'wrong' : 'expected-integrity' } }), {
            status: status === 'mismatch' ? 200 : status,
          });
        };
        try {
          await import(${JSON.stringify(script)});
        } finally {
          console.log(JSON.stringify({ calls, delays }));
        }
      `], { env, encoding: 'utf8' });
      assert.equal(result.status, success ? 0 : 1, result.stderr);
      assert.deepEqual(JSON.parse(result.stdout), { calls: expectedCalls, delays: expectedCalls - 1 });
      const hasSummary = success && summaryMode === 'present';
      assert.equal(existsSync(summary), hasSummary);
      if (hasSummary) assert.match(readFileSync(summary, 'utf8'), /Registry integrity matches/);
      if (expectedCalls === 6 && !success) assert.match(result.stderr, /after 6 attempts/);
    } finally {
      rmSync(directory, { recursive: true, force: true });
    }
  });
}
