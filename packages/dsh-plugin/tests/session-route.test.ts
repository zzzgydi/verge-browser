import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createServer } from 'node:http';
import { connect } from 'node:net';
import { once } from 'node:events';
import { connectionConfig } from '../src/config.js';
import { SessionProxy } from '../src/session.js';

/** Track sockets, because an upgraded one leaves the server's own connection list. */
function track(server: import('node:http').Server) {
  const sockets = new Set<import('node:net').Socket>();
  server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
  return () => { for (const socket of sockets) socket.destroy(); server.closeAllConnections(); };
}

/** A Verge stand-in: issues session tickets, checks the session cookie, and upgrades its socket. */
async function verge() {
  const state = { cookies: new Set<string>(), issued: 0, paths: [] as string[] };
  const server = createServer((req, res) => {
    const url = new URL(req.url!, 'http://x');
    state.paths.push(`${req.method} ${url.pathname}`);
    if (url.pathname.endsWith('/session/apply')) {
      if (req.headers.authorization !== 'Bearer test-token') { res.writeHead(401); res.end('{"message":"denied"}'); return; }
      state.issued += 1;
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ code: 0, message: 'ok', data: { session_url: `http://127.0.0.1:${port}/sandbox/stable-id/session/?ticket=t${state.issued}` } }));
      return;
    }
    const ticket = url.searchParams.get('ticket');
    if (url.pathname === '/sandbox/stable-id/session/' && ticket) {
      state.cookies.add(`verge_session=${ticket}`);
      res.writeHead(302, { location: '/sandbox/stable-id/session/', 'set-cookie': `verge_session=${ticket}; Path=/; HttpOnly` });
      res.end();
      return;
    }
    if (!authorized(req.headers.cookie)) { res.writeHead(401); res.end('denied'); return; }
    res.writeHead(200, { 'content-type': 'text/plain', 'set-cookie': 'verge_session=must-not-leak; Path=/' });
    res.end(`served ${url.pathname}`);
  });
  const authorized = (cookie?: string) => state.cookies.has(cookie ?? '');
  server.on('upgrade', (req, socket) => {
    const target = new URL(req.url!, 'http://x');
    const admitted = target.pathname === '/sandbox/stable-id/session/'
      && (target.searchParams.has('ticket') || authorized(req.headers.cookie));
    if (!admitted) {
      socket.end('HTTP/1.1 401 Unauthorized\r\n\r\n');
      return;
    }
    socket.write('HTTP/1.1 101 Switching Protocols\r\nupgrade: websocket\r\nconnection: Upgrade\r\n\r\n');
    socket.write('upstream-hello');
  });
  const dispose = track(server);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const port = (server.address() as { port: number }).port;
  return {
    state, authorized,
    config: connectionConfig.parse({ baseUrl: `http://127.0.0.1:${port}`, token: 'test-token', sandbox: 'alias' }),
    close: async () => { dispose(); await new Promise<void>(resolve => server.close(() => resolve())); },
  };
}

/** Serve one proxy instance on its own port, as the DSH host does. */
async function host(proxy: SessionProxy) {
  const server = createServer((req, res) => { void proxy.http(req, res); });
  server.on('upgrade', (req, socket, head) => { void proxy.upgrade(req, socket, head); });
  const dispose = track(server);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const port = (server.address() as { port: number }).port;
  return {
    origin: `http://127.0.0.1:${port}`,
    close: async () => { dispose(); await new Promise<void>(resolve => server.close(() => resolve())); },
  };
}

test('session proxy serves the page through its own origin without leaking the Verge cookie', async () => {
  const v = await verge();
  const proxy = new SessionProxy(v.config);
  const app = await host(proxy);
  try {
    const response = await fetch(`${app.origin}/verge-browser/session/`);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'served /sandbox/stable-id/session/');
    assert.equal(response.headers.get('set-cookie'), null);
    const asset = await fetch(`${app.origin}/verge-browser/session/css/client.css`);
    assert.equal(await asset.text(), 'served /sandbox/stable-id/session/css/client.css');
    assert.equal(v.state.issued, 1, 'one ticket serves the whole page');
  } finally { await app.close(); await v.close(); }
});

test('session proxy replaces an expired cookie once and then succeeds', async () => {
  const v = await verge();
  const proxy = new SessionProxy(v.config);
  const app = await host(proxy);
  try {
    assert.equal((await fetch(`${app.origin}/verge-browser/session/`)).status, 200);
    v.state.cookies.clear();
    const retried = await fetch(`${app.origin}/verge-browser/session/`);
    assert.equal(retried.status, 200);
    assert.equal(v.state.issued, 2, 'the proxy requests a new ticket after a rejected cookie');
  } finally { await app.close(); await v.close(); }
});

test('session proxy reports an unreachable Verge without leaking secrets', async () => {
  const v = await verge();
  const proxy = new SessionProxy({ ...v.config, token: 'wrong-token' });
  const app = await host(proxy);
  try {
    const response = await fetch(`${app.origin}/verge-browser/session/`);
    assert.equal(response.status, 502);
    const body = await response.text();
    assert.match(body, /Verge session is unavailable/);
    assert(!body.includes('wrong-token'));
    assert(!body.includes('ticket='));
  } finally { await app.close(); await v.close(); }
});

test('session proxy relays the Xpra socket to Verge', async () => {
  const v = await verge();
  const proxy = new SessionProxy(v.config);
  const app = await host(proxy);
  try {
    const { port } = new URL(app.origin);
    const socket = connect(Number(port), '127.0.0.1');
    await once(socket, 'connect');
    socket.write('GET /verge-browser/session/ HTTP/1.1\r\nHost: localhost\r\nConnection: Upgrade\r\nUpgrade: websocket\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n');
    let received = '';
    socket.on('data', chunk => { received += chunk.toString(); });
    for (let attempt = 0; attempt < 60 && !received.includes('upstream-hello'); attempt++) {
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    socket.destroy();
    assert.match(received, /^HTTP\/1\.1 101/);
    assert.match(received, /upstream-hello/);
  } finally { await app.close(); await v.close(); }
});
