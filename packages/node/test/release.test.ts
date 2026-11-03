import test from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const root = new URL('../../', import.meta.url);
const { version } = JSON.parse(readFileSync(new URL('package.json', root), 'utf8'));
const script = fileURLToPath(new URL('scripts/check-release.mjs', root));

for (const [label, event, refType, refName, requested, valid] of [
  ['matching tag', 'push', 'tag', `verge-browser-v${version}`, '', true],
  ['wrong tag', 'push', 'tag', 'verge-browser-v0.0.0', '', false],
  ['wrong tag prefix', 'push', 'tag', `dsh-plugin-v${version}`, '', false],
  ['branch push', 'push', 'branch', 'main', '', false],
  ['manual branch', 'workflow_dispatch', 'branch', 'main', version, true],
  ['wrong manual version', 'workflow_dispatch', 'branch', 'main', '0.0.0', false],
  ['missing manual version', 'workflow_dispatch', 'branch', 'main', '', false],
  ['manual tag', 'workflow_dispatch', 'tag', `verge-browser-v${version}`, version, true],
  ['manual tag with wrong input', 'workflow_dispatch', 'tag', `verge-browser-v${version}`, '0.0.0', false],
  ['unexpected event', 'pull_request', 'branch', 'main', version, false],
] as const) {
  test(`release version check: ${label}`, () => {
    const run = () => execFileSync(process.execPath, [script], { env: {
      ...process.env, GITHUB_EVENT_NAME: event, GITHUB_REF_TYPE: refType,
      GITHUB_REF_NAME: refName, REQUESTED_VERSION: requested,
    }, stdio: 'pipe' });
    if (valid) assert.doesNotThrow(run);
    else assert.throws(run);
  });
}
