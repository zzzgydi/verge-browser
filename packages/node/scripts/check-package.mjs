import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

const exec = promisify(execFile);
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const manifest = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'));
const directory = await mkdtemp(join(tmpdir(), 'verge-browser-package-'));
console.log(`Checking installed tarball in ${directory} (preserved on failure)`);

const packed = await exec('npm', ['pack', '--json', '--pack-destination', directory], { cwd: root });
const [artifact] = JSON.parse(packed.stdout);
assert.equal(artifact.version, manifest.version);
for (const path of ['package.json', 'README.md', 'LICENSE', 'dist/src/index.js', 'dist/src/index.d.ts', 'dist/src/cli.js']) {
  assert.ok(artifact.files.some(file => file.path === path), `Missing packed file: ${path}`);
}
await writeFile(join(directory, 'package.json'), JSON.stringify({ name: 'verge-package-consumer', private: true, type: 'module' }));
await exec('npm', ['install', '--ignore-scripts', '--no-audit', '--no-fund', '--package-lock=false', join(directory, artifact.filename)], { cwd: directory });

await writeFile(join(directory, 'consumer.ts'), `
import { VergeClient, type BrowserEngine, type CreateSandboxPayload } from 'verge-browser';
import { runCli } from 'verge-browser/cli';
const engine: BrowserEngine = 'camoufox';
const payload: CreateSandboxPayload = { browser_engine: engine };
const client = new VergeClient({ token: 'package-test' });
void client.createSandbox(payload);
void client.browserCommand('fox', { action: 'snapshot', interactive: true });
void runCli;
`);
await exec(process.execPath, [join(root, 'node_modules/typescript/bin/tsc'), '--noEmit', '--strict', '--skipLibCheck', '--target', 'ES2022', '--module', 'NodeNext', '--moduleResolution', 'NodeNext', 'consumer.ts'], { cwd: directory });

const requests = [];
const server = createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = JSON.parse(Buffer.concat(chunks).toString() || '{}');
  requests.push({ method: request.method, url: request.url, authorization: request.headers.authorization, body });
  const failed = body.ref === '@e9999';
  response.writeHead(failed ? 502 : 200, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify({ code: failed ? 502 : 0, message: failed ? 'stale ref (not retried)' : 'ok', data: failed ? null : { id: 'fox', browser_engine: 'camoufox' } }));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const env = { ...process.env, VERGE_BROWSER_URL: `http://127.0.0.1:${server.address().port}`, VERGE_BROWSER_TOKEN: 'package-test' };
const binary = join(directory, 'node_modules/.bin/verge-browser');

try {
  const version = await exec(binary, ['--version'], { env });
  assert.ok(version.stdout.startsWith(`verge-browser/${manifest.version} `), version.stdout);
  const sandboxHelp = await exec(binary, ['sandbox', '--help'], { env });
  assert.match(sandboxHelp.stdout, /--browser-engine/);
  assert.match(sandboxHelp.stdout, /camoufox/);
  const browserHelp = await exec(binary, ['browser', '--help'], { env });
  assert.match(browserHelp.stdout, /snapshot/);
  assert.match(browserHelp.stdout, /--tab/);

  await writeFile(join(directory, 'consumer.mjs'), `
import assert from 'node:assert/strict';
import { VergeClient } from 'verge-browser';
import { runCli } from 'verge-browser/cli';
assert.equal(typeof runCli, 'function');
const client = new VergeClient();
assert.equal((await client.createSandbox({ browser_engine: 'camoufox' })).browser_engine, 'camoufox');
await client.browserCommand('fox', { action: 'snapshot', interactive: true });
`);
  await exec(process.execPath, ['consumer.mjs'], { cwd: directory, env });
  assert.deepEqual(requests.shift().body, { kind: 'xvfb_vnc', browser_engine: 'camoufox' });
  assert.deepEqual(requests.shift(), { method: 'POST', url: '/sandbox/fox/browser/command', authorization: 'Bearer package-test', body: { action: 'snapshot', interactive: true } });

  for (const engine of ['chromium', 'cloakbrowser', 'camoufox']) {
    await exec(binary, ['sandbox', 'create', '--browser-engine', engine, '--json'], { env });
    assert.deepEqual(requests.shift(), { method: 'POST', url: '/sandbox', authorization: 'Bearer package-test', body: { kind: 'xvfb_vnc', browser_engine: engine } });
  }

  const commands = [
    [['open', 'https://example.com', '--tab', 'research'], { action: 'open', url: 'https://example.com', tab: 'research' }],
    [['snapshot', '-i', '--selector', '#main'], { action: 'snapshot', interactive: true, selector: '#main' }],
    [['click', '@e1'], { action: 'click', ref: '@e1' }],
    [['fill', '@e2', ''], { action: 'fill', ref: '@e2', text: '' }],
    [['press', 'Enter'], { action: 'press', key: 'Enter' }],
    [['text', '#result'], { action: 'text', target: '#result' }],
    [['tabs'], { action: 'tabs' }],
    [['switch', '1'], { action: 'switch', index: 1 }],
    [['url'], { action: 'url' }],
    [['title'], { action: 'title' }],
    [['upload', '#file', '/workspace/uploads/test.txt'], { action: 'upload', selector: '#file', path: '/workspace/uploads/test.txt' }],
  ];
  for (const [[action, ...args], payload] of commands) {
    await exec(binary, ['browser', action, 'fox', ...args, '--json'], { env });
    assert.deepEqual(requests.shift(), { method: 'POST', url: '/sandbox/fox/browser/command', authorization: 'Bearer package-test', body: { tab: 'default', ...payload } });
  }

  await assert.rejects(exec(binary, ['browser', 'click', 'fox', '@e9999', '--json'], { env }), error => {
    assert.equal(error.code, 1);
    assert.equal(JSON.parse(error.stderr).error, '502: stale ref (not retried)');
    return true;
  });
  assert.equal(requests.length, 1, 'Failed commands must not be retried');
} finally {
  await new Promise((resolve, reject) => server.close(error => error ? reject(error) : resolve()));
}

if (process.env.VERGE_PACKAGE_OUTPUT_DIR) {
  const output = resolve(process.env.VERGE_PACKAGE_OUTPUT_DIR);
  await mkdir(output, { recursive: true });
  await copyFile(join(directory, artifact.filename), join(output, 'verge-browser.tgz'));
  await writeFile(join(output, 'package-metadata.json'), JSON.stringify({
    name: manifest.name, version: manifest.version, integrity: artifact.integrity,
  }, null, 2) + '\n');
}
await rm(directory, { recursive: true, force: true });
console.log(`verge-browser@${manifest.version}: installed SDK, types, CLI, engine routing and command failures passed`);
