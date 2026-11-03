import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';

export const name = 'verge-profile-check';
export const inject = ['agents', 'tools', 'browserUse', 'ptcRuntime'];

export function apply(ctx) {
  ctx.appReady.onReady(() => {
    void run().catch(error => { console.error(error); ctx.appExit(1); });
  });
  async function run() {
    // Create a real Agent, but never submit a prompt or invoke a model.
    const owner = await ctx.agents.create({ sessionId: `verge-profile-check-${randomUUID()}`, meta: { cwd: process.cwd() } });
    try {
      assert.equal(ctx.browserUse.providerName, 'verge-browser');
      const result = await ctx.tools.execute({
        callId: 'ptc-check', name: 'run_code', agent: owner.agent, signal: new AbortController().signal,
        arguments: { description: 'Verify packed Verge plugin through PTC',
          code: 'const result = await tools["mcp__verge-browser__verge_status"]({}); return result.structuredContent.id;' },
      });
      assert(!result.isError, JSON.stringify(result));
      assert(JSON.stringify(result.value).includes('stable-id'), JSON.stringify(result));
      console.log('VERGE_PROFILE_PTC_PASS');
    } finally { await owner.dispose(); }
    ctx.appExit(0);
  }
}
