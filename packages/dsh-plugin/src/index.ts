import { fileURLToPath } from 'node:url';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Duplex } from 'node:stream';
import type { Context } from '@deepseek-ai/cordis';
import Schema from '@deepseek-ai/schemastery';
import { mountSessionMcp } from '@deepseek-ai/dsh-experimental-browser-use-runtime/mcp';
import { connectionConfig, type ConnectionConfig } from './config.js';
import { SESSION_PREFIX, SESSION_SOCKET, SessionProxy } from './session.js';

export const name = 'verge-browser';
export const inject = ['browserUse', 'agents', 'tools', 'systemPrompt', 'workingDirectory'];
export const Config = Schema.object({
  baseUrl: Schema.string().required().description('Verge API URL (not a CDP or session URL).'),
  token: Schema.string().role('secret').required().description('Verge admin token. Never sent to the model.'),
  sandbox: Schema.string().required().description('Existing sandbox ID or alias. No automatic creation.'),
  requestTimeoutMs: Schema.number().default(30_000),
  toolCallTimeoutMs: Schema.number().default(60_000),
  cdpTicketTtlSec: Schema.number().default(300),
  handoffTtlSec: Schema.number().default(300),
});

/** The route registry of the Web host's HTTP server, declared here so this package needs no host dependency. */
interface WebServer {
  register(route: {
    kind: 'exact' | 'prefix';
    path: string;
    handler: (req: IncomingMessage, res: ServerResponse) => void | Promise<void>;
  }): () => void;
  registerUpgrade(route: { path: string; handler: (req: IncomingMessage, socket: Duplex, head: Buffer) => void | Promise<void> }): () => void;
}

export function apply(ctx: Context, input: ConnectionConfig): void {
  const config = connectionConfig.parse(input);
  mountSessionMcp(ctx, {
    name: 'verge-browser',
    exclusive: true,
    command: process.execPath,
    args: [fileURLToPath(new URL('./bridge.js', import.meta.url))],
    env: { VERGE_DSH_CONFIG: JSON.stringify(config) },
    toolCallTimeoutMs: config.toolCallTimeoutMs,
  });
  // The sidebar frame loads the live session through the Web host, so the page, its assets and
  // its WebSocket stay same-origin with DSH. Headless and desktop compositions own no HTTP
  // server, so these routes follow the service instead of requiring it.
  const proxy = new SessionProxy(config);
  const host = ctx as unknown as { inject(names: string[], run: (scope: { webServer: WebServer }) => void): void };
  host.inject(['webServer'], scope => {
    ctx.effect(() => scope.webServer.register({
      kind: 'prefix',
      path: SESSION_PREFIX,
      handler: (req, res) => proxy.http(req, res),
    }), 'verge-browser: session route');
    ctx.effect(() => scope.webServer.registerUpgrade({
      path: SESSION_SOCKET,
      handler: (req, socket, head) => proxy.upgrade(req, socket, head),
    }), 'verge-browser: session socket');
  });
}
