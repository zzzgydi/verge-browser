import { createServer } from 'node:http';
import { once } from 'node:events';
import { connectionConfig } from '../src/config.js';

export async function fixture(engine = 'camoufox') {
  const calls: { path: string; body: any; method?: string }[] = [];
  let state = 'RUNNING';
  let delay = 0;
  const server = createServer(async (req, res) => {
    let raw = ''; for await (const chunk of req) raw += chunk;
    const path = req.url!;
    const body = raw ? JSON.parse(raw) : undefined;
    calls.push({ path, body, method: req.method });
    if (req.headers.authorization !== 'Bearer test-token') { res.writeHead(401); res.end('{"message":"denied"}'); return; }
    if (path.includes('/browser/command') && delay) await new Promise(r => setTimeout(r, delay));
    const data = path.includes('/browser/command') ? { snapshot: 'button "Save" [ref=e1]', ...body }
      : path.includes('/session/apply') ? { session_url: 'http://localhost/session?ticket=temporary', expires_at: 'soon' }
      : path.includes('/browser/screenshot') ? { data_base64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC', metadata: { width: 1, height: 1 } }
      : path.includes('/files/read') ? { path: '/workspace/note', content: 'hello' }
      : path.includes('/files/list') ? [{ name: 'note', path: '/host/private/note', size: 5, is_dir: false }]
      : path.includes('/files/write') ? { path: '/host/private/path' }
      : { id: 'stable-id', browser_engine: engine, status: state, browser: { viewport: { width: 1280, height: 900 } } };
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ code: 0, message: 'ok', data }));
  });
  server.listen(0, '127.0.0.1'); await once(server, 'listening');
  const address = server.address() as { port: number };
  const config = connectionConfig.parse({ baseUrl: `http://127.0.0.1:${address.port}`, token: 'test-token', sandbox: 'alias' });
  return { config, calls, setState: (s: string) => state = s, setDelay: (ms: number) => delay = ms,
    close: async () => { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())); } };
}

