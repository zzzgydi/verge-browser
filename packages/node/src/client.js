import {
  VergeAuthError,
  VergeConflictError,
  VergeConfigError,
  VergeNotFoundError,
  VergeServerError,
  VergeValidationError,
} from './errors.js';

export class VergeClient {
  constructor(options = {}) {
    this.baseUrl = (options.baseUrl ?? process.env.VERGE_BROWSER_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
    const token = options.token ?? process.env.VERGE_BROWSER_TOKEN;
    if (!token) {
      throw new VergeConfigError('missing token; set VERGE_BROWSER_TOKEN or pass --token');
    }
    this.token = token;
  }

  listSandboxes() { return this.request('GET', '/sandboxes'); }
  createSandbox(payload) { return this.request('POST', '/sandboxes', payload); }
  getSandbox(idOrAlias) { return this.request('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}`); }
  updateSandbox(idOrAlias, payload) { return this.request('PATCH', `/sandboxes/${encodeURIComponent(idOrAlias)}`, payload); }
  async deleteSandbox(idOrAlias) { await this.request('DELETE', `/sandboxes/${encodeURIComponent(idOrAlias)}`); return { ok: true }; }
  pauseSandbox(idOrAlias) { return this.request('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/pause`); }
  resumeSandbox(idOrAlias) { return this.request('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/resume`); }
  getCdpInfo(idOrAlias) { return this.request('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}/browser/cdp/info`); }
  createVncTicket(idOrAlias, payload = {}) {
    return this.request('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/vnc/tickets`, {
      mode: payload.mode ?? 'one_time',
      ...(payload.ttl_sec !== undefined ? { ttl_sec: payload.ttl_sec } : {}),
    });
  }

  async getVncUrl(idOrAlias) {
    const sandbox = await this.getSandbox(idOrAlias);
    const ticket = await this.createVncTicket(String(sandbox.id), { mode: 'one_time' });
    return {
      sandbox_id: sandbox.id,
      alias: sandbox.alias,
      ticket: ticket.ticket,
      url: `${sandbox.browser.vnc_entry_base_url}?ticket=${ticket.ticket}`,
      expires_at: ticket.expires_at,
      mode: ticket.mode,
    };
  }

  async request(method, path, body) {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${this.token}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    if (response.ok) {
      if (response.status === 204) return null;
      const text = await response.text();
      return text ? JSON.parse(text) : null;
    }

    const detail = await this.extractError(response);
    if (response.status === 401) throw new VergeAuthError(detail || 'authentication failed');
    if (response.status === 404) throw new VergeNotFoundError(detail || 'resource not found');
    if (response.status === 409) throw new VergeConflictError(detail || 'request conflict');
    if (response.status === 422) throw new VergeValidationError(detail || 'validation failed');
    throw new VergeServerError(`${response.status}: ${detail || 'request failed'}`);
  }

  async extractError(response) {
    const text = await response.text();
    if (!text) return '';
    try {
      const parsed = JSON.parse(text);
      return typeof parsed.detail === 'string' ? parsed.detail : text;
    } catch {
      return text;
    }
  }
}
