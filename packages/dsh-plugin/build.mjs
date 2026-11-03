import { writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

// Bundle browser helpers so their release-specific manifests do not gate profile rows.
// Agent, MCP, tools and scope imports remain external and share the host's services.
await build({
  entryPoints: ['src/index.ts', 'src/bridge.ts', 'src/registry.ts'],
  outdir: 'dist',
  bundle: true,
  packages: 'external',
  plugins: [{
    name: 'browser-helpers',
    setup(builder) {
      builder.onResolve({ filter: /^@deepseek-ai\/dsh-(browser-use|experimental-browser-use-runtime)(\/|$)/ }, args => ({
        path: fileURLToPath(import.meta.resolve(args.path)),
      }));
    },
  }],
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
