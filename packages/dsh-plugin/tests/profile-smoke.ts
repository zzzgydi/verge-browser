import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { fixture } from './fixture.js';

assert(process.env.DSH_HOME && isAbsolute(process.env.DSH_HOME), 'Set DSH_HOME to a disposable absolute home containing profile verify');
const directory = await mkdtemp(join(tmpdir(), 'verge-profile-'));
const f = await fixture();
try {
  const patch = join(directory, 'check.patch.yml');
  await writeFile(patch, `
- id: verge-browser-registry
  disabled: false
- id: verge-browser
  disabled: false
  config: !!js JSON.parse(process.env.VERGE_DSH_CONFIG)
- id: tools
  config:
    mode: ptc
- insert:
    - id: verge-profile-check
      name: ${JSON.stringify(fileURLToPath(new URL('./profile-check.mjs', import.meta.url)))}
`);
  await new Promise<void>((resolve, reject) => {
    const child = spawn('dsh', ['--profile', 'verify', '--patch', patch], {
      cwd: directory, env: { ...process.env, VERGE_DSH_CONFIG: JSON.stringify(f.config) }, stdio: ['ignore', 'pipe', 'pipe'],
    });
    let output = ''; let timedOut = false;
    child.stdout.on('data', chunk => { output += chunk; process.stdout.write(chunk); });
    child.stderr.on('data', chunk => process.stderr.write(chunk));
    const timer = setTimeout(() => { timedOut = true; child.kill('SIGTERM'); }, 60_000);
    child.on('error', error => { clearTimeout(timer); reject(error); });
    child.on('exit', code => {
      clearTimeout(timer);
      if (code === 0 && !timedOut && output.includes('VERGE_PROFILE_PTC_PASS')) resolve();
      else reject(new Error(`Profile verification failed (exit=${code}, timeout=${timedOut})`));
    });
  });
} finally { await f.close(); await rm(directory, { recursive: true, force: true }); }
