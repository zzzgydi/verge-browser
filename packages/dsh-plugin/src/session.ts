import { request as httpRequest, type IncomingMessage, type ServerResponse } from 'node:http';
import { request as httpsRequest } from 'node:https';
import type { Duplex } from 'node:stream';
import { VergeClient } from '../../node/src/client.js';
import type { ConnectionConfig } from './config.js';
import { redact } from './redact.js';

export const SESSION_PREFIX = '/verge-browser/session';
/** The Xpra client opens its WebSocket on the page path, which the Web host matches exactly. */
export const SESSION_SOCKET = `${SESSION_PREFIX}/`;

const HOP_HEADERS = new Set(['host', 'connection', 'cookie', 'upgrade', 'keep-alive', 'proxy-authorization', 'te', 'trailer']);
const REDIRECTS = new Set([301, 302, 303, 307, 308]);

interface Session {
  cookie: string;
  ticket: string;
  path: string;
}

/**
 * Proxy the live Verge session through the DSH host.
 * The browser then talks only to this origin: the Verge session cookie and the
 * admin token never reach it, and no third-party cookie is involved.
 */
export class SessionProxy {
  private session?: Session;

  constructor(private readonly config: ConnectionConfig) {}

  private async open(): Promise<Session> {
    if (this.session) return this.session;
    const api = new VergeClient({
      baseUrl: this.config.baseUrl,
      token: this.config.token,
      fetchImpl: (input, init) => fetch(input, {
        ...init, redirect: 'manual', signal: AbortSignal.timeout(this.config.requestTimeoutMs),
      }),
    });
    const ticket = await api.createSessionTicket(this.config.sandbox, { mode: 'reusable', ttl_sec: this.config.handoffTtlSec });
    const response = await fetch(ticket.session_url, {
      redirect: 'manual', signal: AbortSignal.timeout(this.config.requestTimeoutMs),
    });
    const cookie = (response.headers as Headers & { getSetCookie?(): string[] }).getSetCookie?.()
      ?.map(value => value.split(';')[0]).filter(value => value.includes('=')).join('; ');
    await response.body?.cancel();
    if (!cookie) throw new Error(`Verge issued no session cookie (HTTP ${response.status})`);
    this.session = {
      cookie,
      ticket: ticket.ticket,
      path: new URL(ticket.session_url).pathname.replace(/\/$/, ''),
    };
    return this.session;
  }

  private expire(): void { this.session = undefined; }

  private send(path: string, method: string, headers: IncomingMessage['headers'], cookie: string, upgrade = false) {
    const base = new URL(this.config.baseUrl);
    const outgoing = { ...headers };
    for (const name of HOP_HEADERS) delete outgoing[name];
    if (upgrade) {
      outgoing.connection = 'Upgrade';
      outgoing.upgrade = headers.upgrade ?? 'websocket';
    }
    return (base.protocol === 'https:' ? httpsRequest : httpRequest)({
      protocol: base.protocol,
      hostname: base.hostname,
      port: base.port || undefined,
      method,
      path,
      headers: { ...outgoing, host: base.host, cookie },
    });
  }

  /** Copy one upstream response to the browser without its Verge cookie or its inline policy. */
  private relay(response: IncomingMessage, res: ServerResponse): void {
    const headers = { ...response.headers };
    delete headers['set-cookie'];
    delete headers['content-security-policy'];
    delete headers['content-security-policy-report-only'];
    res.writeHead(response.statusCode ?? 502, headers);
    response.pipe(res);
  }

  private fail(res: ServerResponse, error: unknown): void {
    if (res.headersSent) { res.destroy(); return; }
    res.writeHead(502, { 'content-type': 'text/plain; charset=utf-8', 'cache-control': 'no-store' });
    res.end(`Verge session is unavailable.\n${redact(error instanceof Error ? error.message : String(error), this.config.token)}\n`);
  }

  /** Resolve one upstream response for a bodyless request. */
  private async read(session: Session, path: string, headers: IncomingMessage['headers']): Promise<IncomingMessage> {
    return new Promise((resolve, reject) => {
      const upstream = this.send(path, 'GET', headers, session.cookie);
      upstream.on('response', resolve);
      upstream.on('error', reject);
      upstream.end();
    });
  }

  /**
   * Fetch the Xpra entry page. Verge answers with a session cookie and a redirect that drops
   * the ticket, so follow that hop here: the browser must never see a Verge URL.
   */
  private async entry(session: Session, headers: IncomingMessage['headers'], res: ServerResponse, refresh: boolean): Promise<void> {
    const base = new URL(this.config.baseUrl);
    let path = `${session.path}/?ticket=${encodeURIComponent(session.ticket)}`;
    let response = await this.read(session, path, headers);
    for (let hop = 0; hop < 3; hop++) {
      const location = response.headers.location;
      if (!REDIRECTS.has(response.statusCode ?? 0) || !location) break;
      const next = new URL(location, base);
      response.resume();
      if (next.origin !== base.origin || !next.pathname.startsWith(session.path)) break;
      path = `${next.pathname}${next.search}`;
      response = await this.read(session, path, headers);
    }
    if (response.statusCode === 401 && refresh) {
      response.resume();
      this.expire();
      return this.entry(await this.open(), headers, res, false);
    }
    this.relay(response, res);
  }

  /** Serve one proxied request; a rejected cookie is replaced once before giving up. */
  http(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const suffix = (req.url ?? SESSION_PREFIX).slice(SESSION_PREFIX.length) || '/';
    return this.forward(req, res, suffix, true);
  }

  private async forward(req: IncomingMessage, res: ServerResponse, suffix: string, refresh: boolean): Promise<void> {
    try {
      const session = await this.open();
      const method = req.method ?? 'GET';
      const pathname = suffix.split('?')[0];
      if ((pathname === '/' || pathname === '') && (method === 'GET' || method === 'HEAD')) {
        await this.entry(session, req.headers, res, refresh);
        return;
      }
      const upstream = this.send(`${session.path}${suffix}`, method, req.headers, session.cookie);
      upstream.on('response', async response => {
        if (response.statusCode === 401 && refresh && (method === 'GET' || method === 'HEAD')) {
          response.resume();
          this.expire();
          await this.forward(req, res, suffix, false).catch(error => this.fail(res, error));
          return;
        }
        this.relay(response, res);
      });
      upstream.on('error', error => this.fail(res, error));
      req.pipe(upstream);
    } catch (error) {
      this.fail(res, error);
    }
  }

  /** Relay the Xpra WebSocket to Verge over one upstream upgrade. */
  async upgrade(req: IncomingMessage, socket: Duplex, head: Buffer): Promise<void> {
    try {
      const session = await this.open();
      const upstream = this.send(`${session.path}/?ticket=${encodeURIComponent(session.ticket)}`, 'GET', req.headers, session.cookie, true);
      upstream.on('upgrade', (response, upstreamSocket, upstreamHead) => {
        const lines = ['HTTP/1.1 101 Switching Protocols'];
        for (let index = 0; index < response.rawHeaders.length; index += 2) {
          lines.push(`${response.rawHeaders[index]}: ${response.rawHeaders[index + 1]}`);
        }
        socket.write(`${lines.join('\r\n')}\r\n\r\n`);
        if (upstreamHead.length) socket.write(upstreamHead);
        if (head.length) upstreamSocket.write(head);
        upstreamSocket.pipe(socket);
        socket.pipe(upstreamSocket);
        for (const stream of [socket, upstreamSocket]) {
          stream.on('error', () => { socket.destroy(); upstreamSocket.destroy(); });
          stream.on('close', () => { socket.destroy(); upstreamSocket.destroy(); });
        }
      });
      upstream.on('response', response => {
        // The ticket or cookie expired while the page stayed open; the client reconnects later.
        this.expire();
        socket.end(`HTTP/1.1 ${response.statusCode} ${response.statusMessage}\r\nconnection: close\r\n\r\n`);
      });
      upstream.on('error', () => socket.destroy());
      upstream.end();
    } catch {
      socket.destroy();
    }
  }
}
