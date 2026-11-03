import { writeFile } from 'node:fs/promises';
import { build } from 'esbuild';

// Bundle the matching in-repository SDK, but share DSH services with the host.
await build({
  entryPoints: ['src/index.ts', 'src/bridge.ts'],
  outdir: 'dist',
  bundle: true,
  packages: 'external',
  platform: 'node',
  format: 'esm',
  target: 'node22',
});

// The Web shell loads client bundles through window.__ModuleLoader__: it supplies the CommonJS
// module scope below and resolves the baseline modules (react) from its own table.
const client = await build({
  entryPoints: ['src/client.ts'],
  bundle: true,
  packages: 'external',
  platform: 'browser',
  format: 'cjs',
  target: 'es2022',
  write: false,
});
await writeFile('dist/client.js', [
  'window.__ModuleLoader__.load({',
  "\tid: 'dsh-plugin-verge-browser',",
  '\tfactory: (require) => {',
  '\t\tvar module = { exports: {} };',
  '\t\tvar exports = module.exports;',
  client.outputFiles[0].text.trimEnd(),
  '\t\treturn module.exports;',
  '\t}',
  '});',
  '',
].join('\n'));
