import {
  VergeAuthError,
  VergeConflictError,
  VergeConfigError,
  VergeNotFoundError,
  VergeServerError,
  VergeValidationError,
} from './errors.js';

export interface BrowserInfo {
  cdp_url?: string;
  vnc_entry_base_url: string;
  browser_version?: string | null;
  protocol_version?: string | null;
}

export interface SandboxResponse {
  id: string;
  alias?: string | null;
  width?: number;
  height?: number;
  browser: BrowserInfo;
}

export interface VncTicketResponse {
  ticket: string;
  mode: 'one_time' | 'reusable' | 'permanent';
  expires_at: string | null;
}

export interface CdpInfoResponse {
  cdp_url: string;
  browser_version?: string | null;
  protocol_version?: string | null;
}

export interface CreateSandboxPayload {
  alias?: string;
  width: number;
  height: number;
  default_url?: string;
  image?: string;
}

export interface UpdateSandboxPayload {
  alias: string;
}

export interface RequestErrorBody {
  detail?: unknown;
}

export interface FetchLike {
  (input: string, init?: RequestInit): Promise<Response>;
}

export interface VergeClientOptions {
  baseUrl?: string;
  token?: string;
  fetchImpl?: FetchLike;
}

export interface VncUrlResponse {
  sandbox_id: string;
  alias?: string | null | undefined;
  ticket: string;
  url: string;
  expires_at: string | null;
  mode: VncTicketResponse['mode'];
}

export class VergeClient {
  private readonly baseUrl: string;
  private readonly token: string;
  private readonly fetchImpl: FetchLike;

  constructor(options: VergeClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? process.env.VERGE_BROWSER_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '');
    const token = options.token ?? process.env.VERGE_BROWSER_TOKEN;
    if (!token) {
      throw new VergeConfigError('missing token; set VERGE_BROWSER_TOKEN or pass --token');
    }
    this.token = token;
    this.fetchImpl = options.fetchImpl ?? fetch;
  }

  listSandboxes(): Promise<SandboxResponse[]> {
    return this.request<SandboxResponse[]>('GET', '/sandboxes');
  }

  createSandbox(payload: CreateSandboxPayload): Promise<SandboxResponse> {
    return this.request<SandboxResponse>('POST', '/sandboxes', payload);
  }

  getSandbox(idOrAlias: string): Promise<SandboxResponse> {
    return this.request<SandboxResponse>('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}`);
  }

  updateSandbox(idOrAlias: string, payload: UpdateSandboxPayload): Promise<SandboxResponse> {
    return this.request<SandboxResponse>('PATCH', `/sandboxes/${encodeURIComponent(idOrAlias)}`, payload);
  }

  async deleteSandbox(idOrAlias: string): Promise<{ ok: true }> {
    await this.request<null>('DELETE', `/sandboxes/${encodeURIComponent(idOrAlias)}`);
    return { ok: true };
  }

  pauseSandbox(idOrAlias: string): Promise<{ ok: boolean }> {
    return this.request<{ ok: boolean }>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/pause`);
  }

  resumeSandbox(idOrAlias: string): Promise<{ ok: boolean }> {
    return this.request<{ ok: boolean }>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/resume`);
  }

  getCdpInfo(idOrAlias: string): Promise<CdpInfoResponse> {
    return this.request<CdpInfoResponse>('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}/browser/cdp/info`);
  }

  createVncTicket(idOrAlias: string, payload: { mode?: VncTicketResponse['mode']; ttl_sec?: number } = {}): Promise<VncTicketResponse> {
    return this.request<VncTicketResponse>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/vnc/tickets`, {
      mode: payload.mode ?? 'one_time',
      ...(payload.ttl_sec !== undefined ? { ttl_sec: payload.ttl_sec } : {}),
    });
  }

  async getVncUrl(idOrAlias: string): Promise<VncUrlResponse> {
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

  private async request<T>(method: string, path: string, body?: object): Promise<T> {
    const init: RequestInit = {
      method,
      headers: {
        Authorization: `Bearer ${this.token}`,
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
    };
    if (body) {
      init.body = JSON.stringify(body);
    }

    const response = await this.fetchImpl(`${this.baseUrl}${path}`, init);

    if (response.ok) {
      if (response.status === 204) {
        return null as T;
      }
      const text = await response.text();
      return text ? (JSON.parse(text) as T) : (null as T);
    }

    const detail = await this.extractError(response);
    if (response.status === 401) throw new VergeAuthError(detail || 'authentication failed');
    if (response.status === 404) throw new VergeNotFoundError(detail || 'resource not found');
    if (response.status === 409) throw new VergeConflictError(detail || 'request conflict');
    if (response.status === 422) throw new VergeValidationError(detail || 'validation failed');
    throw new VergeServerError(`${response.status}: ${detail || 'request failed'}`);
  }

  private async extractError(response: Response): Promise<string> {
    const text = await response.text();
    if (!text) return '';
    try {
      const parsed = JSON.parse(text) as RequestErrorBody;
      return typeof parsed.detail === 'string' ? parsed.detail : text;
    } catch {
      return text;
    }
  }
}
