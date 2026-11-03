import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';

test('the package admits the DSH 0.2 line without installing a private host runtime', async () => {
  const manifest = JSON.parse(await readFile(new URL('../package.json', import.meta.url), 'utf8'));
  assert.equal(manifest.engines.dsh, '^0.2.0');
  for (const name of ['agent', 'mcp-client', 'scope', 'system-prompt', 'tools', 'working-directory']) {
    assert.equal(manifest.peerDependencies[`@deepseek-ai/dsh-${name}`], '^0.2.0');
  }
  assert(!Object.keys(manifest.dependencies).some(name => name.startsWith('@deepseek-ai/dsh-')));
  assert.equal(manifest.exports['./registry'], './dist/registry.js');
  assert(manifest.files.includes('THIRD_PARTY_NOTICES.md'));
  const patch = await readFile(new URL('../cordis.patch.yml', import.meta.url), 'utf8');
  assert(patch.includes('name: dsh-plugin-verge-browser/registry'));
  assert(!patch.includes("name: '@deepseek-ai/dsh-browser-use'"));
});

test('built browser helpers keep MCP and scope imports shared with the host', async () => {
  const provider = await readFile(new URL('../dist/index.js', import.meta.url), 'utf8');
  const registry = await readFile(new URL('../dist/registry.js', import.meta.url), 'utf8');
  for (const source of [provider, registry]) {
    assert(!/from ["']@deepseek-ai\/dsh-(browser-use|experimental-browser-use-runtime)(\/[^"']*)?["']/.test(source));
  }
  assert.match(provider, /from ["']@deepseek-ai\/dsh-scope["']/);
  assert.match(provider, /from ["']@deepseek-ai\/dsh-mcp-client["']/);
  assert.match(registry, /from ["']@deepseek-ai\/cordis["']/);
});
