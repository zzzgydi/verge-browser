import { posix } from 'node:path';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { InMemoryTransport } from '@modelcontextprotocol/sdk/inMemory.js';
import type { CallToolResult, Tool } from '@modelcontextprotocol/sdk/types.js';
import { createConnection } from '@playwright/mcp';
import { chromium, type Browser } from 'playwright';
import Ajv from 'ajv/dist/2020.js';
import { VergeClient, type SandboxResponse } from '../../node/src/client.js';
import type { ConnectionConfig } from './config.js';
import { redact } from './redact.js';
import { sharedTools, camoufoxTools, playwrightTools } from './tools.js';

const MAX_TEXT = 64 * 1024;
const MAX_RESPONSE = 24 * 1024 * 1024;
const jsonResult = (value: Record<string, unknown>): CallToolResult => ({
  content: [{ type: 'text', text: JSON.stringify(value) }], structuredContent: value,
});

function workspacePath(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/workspace/') || value.includes('\0')) {
    if (value === '/workspace') return value;
    throw new Error('Use an absolute /workspace path');
  }
  const path = posix.normalize(value);
  if (!path.startsWith('/workspace/')) throw new Error('Path must stay within /workspace');
  return path;
}

export class AttachedBrowser {
  private sandbox!: SandboxResponse;
  private browser?: Browser;
  private mcp?: Client;
  private upstream?: Awaited<ReturnType<typeof createConnection>>;
  private state: 'automation' | 'handoff' | 'interrupted' = 'automation';
  private readonly lifetime = new AbortController();
  private tail: Promise<unknown> = Promise.resolve();
  private validators = new Map<string, ReturnType<Ajv['compile']>>();
  private catalog: Tool[] = [];

  constructor(private readonly config: ConnectionConfig) {}

  private client(signal: AbortSignal): VergeClient {
    return new VergeClient({ baseUrl: this.config.baseUrl, token: this.config.token, fetchImpl: async (input, init) => {
      const response = await fetch(input, {
        ...init, redirect: 'error',
        signal: AbortSignal.any([signal, this.lifetime.signal, AbortSignal.timeout(this.config.requestTimeoutMs)]),
      });
      // Bound response acquisition as well as model-visible text, including chunked bodies.
      const reader = response.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader) {
        try {
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            size += value.byteLength;
            if (size > MAX_RESPONSE) throw new Error('Verge response exceeds 24 MiB');
            chunks.push(value);
          }
        } finally { await reader.cancel(); }
      }
      return new Response(size ? Buffer.concat(chunks) : null, { status: response.status, headers: response.headers });
    } });
  }

  async initialize(): Promise<void> {
    this.sandbox = await this.client(this.lifetime.signal).getSandbox(this.config.sandbox);
    this.assertReady(this.sandbox);
    // Discovery must not connect, create, navigate, or issue a ticket (DSH can probe twice).
    let native: Tool[];
    if (this.sandbox.browser_engine === 'camoufox') native = camoufoxTools;
    else {
      const server = await createConnection({ browser: { browserName: 'chromium', isolated: false } }, async () => {
        throw new Error('Tool discovery cannot acquire a browser');
      });
      const client = new Client({ name: 'verge-catalog', version: '0.1.0' });
      const [a, b] = InMemoryTransport.createLinkedPair();
      try {
        await server.connect(a);
        await client.connect(b);
        native = (await client.listTools()).tools.filter(tool => playwrightTools.has(tool.name));
        // The upstream snapshot writer targets the MCP host, not the remote workspace.
        for (const tool of native) {
          if (tool.name === 'browser_snapshot') delete tool.inputSchema.properties?.filename;
          if (tool.name === 'browser_tabs') {
            tool.inputSchema.properties!.action = { type: 'string', enum: ['list', 'new', 'select'] };
          }
        }
      } finally { await client.close(); await server.close(); }
    }
    this.catalog = [...sharedTools, ...native];
    const ajv = new Ajv({ strict: false });
    for (const tool of this.catalog) this.validators.set(tool.name, ajv.compile(tool.inputSchema));
  }

  tools(): Tool[] { return this.catalog; }

  private assertReady(sandbox: SandboxResponse): void {
    if (!['chromium', 'cloakbrowser', 'camoufox'].includes(sandbox.browser_engine)) throw new Error('Missing or unsupported browser_engine; use a matching Verge API');
    if (sandbox.status !== 'RUNNING') throw new Error(`Sandbox is ${sandbox.status}, not RUNNING; inspect it in Verge`);
  }

  private async current(signal: AbortSignal): Promise<SandboxResponse> {
    const value = await this.client(signal).getSandbox(this.sandbox.id);
    this.assertReady(value);
    if (value.browser_engine !== this.sandbox.browser_engine) throw new Error('Browser engine changed; unload and reattach');
    return value;
  }

  private async disconnect(): Promise<void> {
    // This is a CDP client disconnect, never context.close() or remote browser shutdown.
    const handles = [this.mcp, this.upstream, this.browser];
    this.mcp = undefined;
    this.upstream = undefined;
    this.browser = undefined;
    const results = await Promise.allSettled(handles.map(handle => handle?.close()));
    const errors = results.filter(result => result.status === 'rejected').map(result => result.reason);
    if (errors.length) throw new Error(`Disconnect failed: ${errors.map(error => this.safeError(error)).join('; ')}`);
  }

  private async connect(signal: AbortSignal): Promise<Client> {
    if (this.mcp && this.browser?.isConnected()) return this.mcp;
    if (this.mcp) throw new Error('CDP disconnected; explicitly call verge_resume, then take a fresh snapshot');
    const ticket = await this.client(signal).getCdpInfo(this.sandbox.id, { mode: 'reusable', ttl_sec: this.config.cdpTicketTtlSec });
    const endpoint = new URL(ticket.cdp_url);
    const base = new URL(this.config.baseUrl);
    if (!['ws:', 'wss:'].includes(endpoint.protocol) || endpoint.host !== base.host || endpoint.username || endpoint.password
      || (base.protocol === 'https:' && endpoint.protocol !== 'wss:')) {
      throw new Error('CDP endpoint must use the configured Verge host without downgrading HTTPS');
    }
    try {
      this.browser = await chromium.connectOverCDP(ticket.cdp_url, { timeout: this.config.requestTimeoutMs });
      signal.throwIfAborted();
      const context = this.browser.contexts()[0];
      if (!context) throw new Error('Attached browser has no default context');
      this.upstream = await createConnection({
        browser: { browserName: 'chromium', isolated: false },
        timeouts: { action: this.config.requestTimeoutMs, navigation: this.config.requestTimeoutMs },
      }, async () => context);
      this.mcp = new Client({ name: 'verge-browser', version: '0.1.0' });
      const [a, b] = InMemoryTransport.createLinkedPair();
      await this.upstream.connect(a);
      await this.mcp.connect(b);
      signal.throwIfAborted();
      return this.mcp;
    } catch (error) {
      await this.disconnect().catch(cleanup => { throw new Error(`${this.safeError(error)}; ${this.safeError(cleanup)}`); });
      throw error;
    }
  }

  call(name: string, args: Record<string, unknown>, signal: AbortSignal): Promise<CallToolResult> {
    const work = this.tail.then(async () => {
      const active = AbortSignal.any([signal, this.lifetime.signal, AbortSignal.timeout(this.config.toolCallTimeoutMs)]);
      active.throwIfAborted();
      const validate = this.validators.get(name);
      if (!validate) throw new Error(`Unknown tool: ${name}`);
      if (!validate(args)) throw new Error(`Invalid arguments: ${JSON.stringify(validate.errors)}`);
      if (this.state !== 'automation' && !['verge_status', 'verge_handoff', 'verge_resume'].includes(name)) {
        throw new Error(`Automation is ${this.state}; explicitly call verge_resume after the human finishes or the connection is ready`);
      }
      try { return await this.execute(name, args, active); }
      catch (error) {
        if (name.startsWith('browser_') || this.state === 'interrupted') {
          this.state = 'interrupted';
          await this.disconnect().catch(cleanup => { throw new Error(`${this.safeError(error)}; ${this.safeError(cleanup)}`); });
        }
        throw error;
      }
    });
    this.tail = work.catch(() => {});
    return work.catch(error => ({ isError: true, content: [{ type: 'text', text: this.safeError(error) }] }));
  }

  private safeError(error: unknown): string {
    return redact(String(error instanceof Error ? error.message : error), this.config.token);
  }

  private async execute(name: string, args: Record<string, unknown>, signal: AbortSignal): Promise<CallToolResult> {
    const api = this.client(signal);
    if (name === 'verge_status') {
      const sandbox = await api.getSandbox(this.sandbox.id);
      return jsonResult({ id: sandbox.id, engine: sandbox.browser_engine, status: sandbox.status,
        viewport: sandbox.browser?.viewport, automation: this.state });
    }
    await this.current(signal);
    if (name === 'verge_handoff') {
      this.state = 'handoff';
      await this.disconnect();
      const ticket = await api.createSessionTicket(this.sandbox.id, { mode: 'one_time', ttl_sec: this.config.handoffTtlSec });
      return jsonResult({ sandbox_id: this.sandbox.id, automation: this.state, url: ticket.session_url, expires_at: ticket.expires_at });
    }
    if (name === 'verge_resume') {
      await this.disconnect();
      this.state = 'automation';
      return jsonResult({ automation: this.state, next: 'Take a fresh snapshot before acting. Old refs are invalid.' });
    }
    if (name === 'verge_screenshot') {
      const shot = await api.getBrowserScreenshot(this.sandbox.id, { type: (args.type ?? 'page') as 'page' | 'window', format: 'png' });
      return { content: [{ type: 'text', text: JSON.stringify(shot.metadata) }, { type: 'image', mimeType: 'image/png', data: shot.data_base64 }] };
    }
    if (name === 'verge_files_list') {
      const path = workspacePath(args.path ?? '/workspace');
      const files = await api.listFiles(this.sandbox.id, path);
      return jsonResult({ files: files.map(file => ({ ...file, path: posix.join(path, file.name) })) });
    }
    if (name === 'verge_file_read') {
      const result = await api.readFile(this.sandbox.id, workspacePath(args.path));
      if (Buffer.byteLength(result.content) > MAX_TEXT) throw new Error('Text file exceeds 64 KiB; use the Verge file CLI');
      return jsonResult({ path: args.path, content: result.content });
    }
    if (name === 'verge_file_write') {
      const path = workspacePath(args.path);
      const content = args.content as string;
      if (Buffer.byteLength(content) > MAX_TEXT) throw new Error('Text exceeds 64 KiB');
      await api.writeFile(this.sandbox.id, { path, content, overwrite: args.overwrite === true });
      return jsonResult({ path });
    }
    if (this.sandbox.browser_engine === 'camoufox') {
      if (name === 'verge_upload') args = { ...args, path: workspacePath(args.path) };
      if (name === 'verge_snapshot') args = { interactive: true, ...args };
      try {
        return jsonResult(await api.browserCommand(this.sandbox.id, {
          ...args as Record<string, string>, action: name.slice('verge_'.length),
        }));
      } catch (error) {
        // An accepted HTTP command can outlive cancellation or a lost response.
        if (['verge_open', 'verge_click', 'verge_fill', 'verge_press', 'verge_switch', 'verge_upload'].includes(name)) {
          this.state = 'interrupted';
        }
        throw error;
      }
    }
    const mcp = await this.connect(signal);
    const abort = () => { this.state = 'interrupted'; void this.browser?.close().catch(() => {}); };
    signal.addEventListener('abort', abort, { once: true });
    try {
      signal.throwIfAborted();
      const result = await mcp.callTool({ name, arguments: args }, undefined, { signal, timeout: this.config.toolCallTimeoutMs });
      signal.throwIfAborted();
      if (result.isError) {
        throw new Error((result as CallToolResult).content.filter(block => block.type === 'text')
          .map(block => block.text).join('\n') || 'Playwright tool failed');
      }
      return result as CallToolResult;
    } finally { signal.removeEventListener('abort', abort); }
  }

  async close(): Promise<void> {
    this.lifetime.abort(new Error('Verge bridge is closing'));
    await this.tail;
    await this.disconnect();
  }
}
