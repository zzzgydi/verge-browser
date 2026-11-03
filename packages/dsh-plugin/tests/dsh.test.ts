import assert from 'node:assert/strict';
import { test } from 'node:test';
import { Context } from '@deepseek-ai/cordis';
import BrowserUse from '@deepseek-ai/dsh-browser-use';
import { BrowserUseProviderName } from '@deepseek-ai/dsh-browser-use/brand';
import Agents, { type Agent } from '@deepseek-ai/dsh-agent';
import Tools from '@deepseek-ai/dsh-tools';
import SystemPrompt from '@deepseek-ai/dsh-system-prompt';
import LocalAttachments from '@deepseek-ai/dsh-attachment-local';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createScope } from '@deepseek-ai/dsh-scope';
import { fixture } from './fixture.js';

test('real Cordis provider scopes MCP tools to one live Agent and disposes cleanly', async () => {
  const f = await fixture();
  const home = await mkdtemp(join(tmpdir(), 'verge-dsh-'));
  const ctx = new Context();
  const owners: ReturnType<typeof createScope>[] = [];
  const unregister: (() => any)[] = [];
  try {
    await ctx.plugin(SystemPrompt, {});
    await ctx.plugin(Tools);
    await ctx.plugin(Agents);
    await ctx.plugin(BrowserUse);
    ctx.provide('workingDirectory');
    ctx.set('workingDirectory', { ensure: async () => process.cwd() } as any);
    let injected!: Context;
    await ctx.inject(['agents', 'tools', 'systemPrompt', 'workingDirectory', 'browserUse'], inner => { injected = inner; });
    const plugin = await import(new URL('../dist/index.js', import.meta.url).href);
    const mounted = ctx.plugin(plugin, f.config);
    await mounted;
    assert.equal(ctx.browserUse.providerName, 'verge-browser');
    assert.throws(() => ctx.browserUse.register(BrowserUseProviderName('other')), /already registered/);
    for (const id of ['first', 'second']) {
      const agent = { id } as Agent;
      const scope = createScope(injected, agent); owners.push(scope);
      Object.assign(agent, { ctx: scope.ctx, session: { id, requestHeader: () => ({config:{provider:'test',model:'test'}}) } });
      const registration = scope.ctx.agents.register(agent); unregister.push(registration);
      await registration;
      const names = ctx.tools.schemas(agent).map(t => t.name);
      if (id === 'first') {
        assert(names.includes('mcp__verge-browser__verge_status'));
        const result = await ctx.tools.execute({ callId: 'test-call' as any, name: 'mcp__verge-browser__verge_status', arguments: {}, agent, signal: new AbortController().signal });
        assert(!result.isError, JSON.stringify(result));
        assert(JSON.stringify(result.value).includes('stable-id'));
        const before = f.calls.length;
        const unguard = ctx.tools.guard(exec => exec.name.endsWith('verge_file_write') ? 'Test policy denies writes' : undefined);
        const denied = await ctx.tools.execute({ callId: 'denied' as any, name: 'mcp__verge-browser__verge_file_write', arguments: {path:'/workspace/no', content:'x'}, agent, signal: new AbortController().signal });
        assert(denied.isError); assert.equal(f.calls.length, before); unguard();
        const image = await ctx.tools.execute({ callId: 'image' as any, name: 'mcp__verge-browser__verge_screenshot', arguments: {}, agent, signal: new AbortController().signal });
        assert(!image.isError);
        assert(JSON.stringify(image.content).includes('no attachment store'));
        assert(JSON.stringify(image.value).includes('iVBORw0KGgo'));
        await ctx.plugin(LocalAttachments, { dshHome: home });
        ctx.provide('llm');
        ctx.set('llm', { resolveModelInfo: async () => ({ inputModalities: ['image'] }) } as any);
        const admitted = await ctx.tools.execute({ callId: 'admitted' as any, name: 'mcp__verge-browser__verge_screenshot', arguments: {}, agent, signal: new AbortController().signal });
        assert(!admitted.isError);
        const block = admitted.content.find(block => block.type === 'image');
        assert(block, JSON.stringify(admitted.content));
        const stored = await ctx.attachments.readImage(block.attachment);
        assert(stored);
        assert.equal(ctx.tools.schemas().filter(t => t.name.startsWith('mcp__verge-browser__')).length, 0);
      } else assert(!names.some(n => n.startsWith('mcp__verge-browser__')));
    }
    await mounted.dispose();
    assert.equal(ctx.browserUse.providerName, undefined);
    assert(!f.calls.some(c => c.method === 'DELETE'));
  } finally {
    for (const scope of owners) await scope.dispose();
    await ctx.fiber.dispose(); await f.close(); await rm(home, { recursive: true, force: true });
  }
});
