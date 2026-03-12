import {
  VergeAuthError,
  VergeConflictError,
  VergeConfigError,
  VergeNotFoundError,
  VergeServerError,
  VergeValidationError,
} from './errors.js';

export type JsonPrimitive = boolean | number | string | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };
export type JsonObject = { [key: string]: JsonValue };
export type SandboxStatus = 'STARTING' | 'RUNNING' | 'STOPPED' | 'FAILED' | 'DEGRADED';
export type VncTicketMode = 'one_time' | 'reusable' | 'permanent';
export type ScreenshotFormat = 'png' | 'jpeg' | 'webp';
export type ScreenshotType = 'window' | 'page';
export type MouseButton = 'left' | 'middle' | 'right';
export type BrowserActionType =
  | 'MOVE_TO'
  | 'CLICK'
  | 'DOUBLE_CLICK'
  | 'RIGHT_CLICK'
  | 'MOUSE_DOWN'
  | 'MOUSE_UP'
  | 'DRAG_TO'
  | 'SCROLL'
  | 'TYPE_TEXT'
  | 'KEY_PRESS'
  | 'HOTKEY'
  | 'WAIT';

export interface ViewportInfo {
  width: number;
  height: number;
}

export interface BrowserInfo {
  cdp_url: string;
  vnc_entry_base_url: string;
  vnc_ticket_endpoint: string;
  browser_version?: string | null;
  protocol_version?: string | null;
  viewport: ViewportInfo;
}

export interface SandboxResponse {
  id: string;
  alias?: string | null;
  status: SandboxStatus;
  created_at: string;
  updated_at: string;
  last_active_at: string;
  width: number;
  height: number;
  metadata: JsonObject;
  browser: BrowserInfo;
  container_id?: string | null;
}

export interface VncTicketResponse {
  ticket: string;
  mode: VncTicketMode;
  ttl_sec: number | null;
  expires_at: string | null;
}

export interface CdpInfoResponse {
  cdp_url: string;
  browser_version?: string | null;
  protocol_version?: string | null;
}

export interface CreateSandboxPayload {
  alias?: string;
  width?: number;
  height?: number;
  default_url?: string;
  image?: string;
  metadata?: JsonObject;
}

export interface UpdateSandboxPayload {
  alias?: string;
  metadata?: JsonObject;
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
  alias?: string | null;
  ticket: string;
  url: string;
  expires_at: string | null;
  mode: VncTicketMode;
  ttl_sec: number | null;
}

export interface BrowserViewportRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ActiveWindowInfo {
  window_id: string | null;
  x: number;
  y: number;
  title: string;
}

export interface BrowserInfoResponse {
  browser_version?: string | null;
  protocol_version?: string | null;
  web_socket_debugger_url_present: boolean;
  viewport: BrowserViewportRect;
}

export interface BrowserViewportResponse {
  window_viewport: BrowserViewportRect;
  page_viewport: BrowserViewportRect;
  active_window: ActiveWindowInfo;
}

export interface ScreenshotMetadata {
  width: number;
  height: number;
  page_viewport: BrowserViewportRect;
  window_viewport: BrowserViewportRect;
  window_id?: string | null;
}

export interface ScreenshotResponse {
  type: ScreenshotType;
  format: ScreenshotFormat;
  media_type: string;
  metadata: ScreenshotMetadata;
  data_base64: string;
}

export interface BrowserAction {
  type: BrowserActionType;
  x?: number;
  y?: number;
  button?: MouseButton;
  text?: string;
  key?: string;
  keys?: string[];
  duration_ms?: number;
  delta_x?: number;
  delta_y?: number;
}

export interface BrowserActionsPayload {
  actions: BrowserAction[];
  continue_on_error?: boolean;
  screenshot_after?: boolean;
}

export interface BrowserActionsResponse {
  ok: boolean;
  executed: number;
  screenshot_after: boolean;
  errors: string[];
}

export interface RestartBrowserPayload {
  level?: 'hard';
}

export interface RestartBrowserResponse {
  ok: boolean;
  level: 'hard';
}

export interface FileEntry {
  name: string;
  path: string;
  size: number;
  is_dir: boolean;
  modified_at: string;
}

export interface ReadFileResponse {
  path: string;
  content: string;
}

export interface WriteFilePayload {
  path: string;
  content: string;
  overwrite?: boolean;
}

export interface WriteFileResponse {
  path: string;
}

export interface UploadFilePayload {
  filename: string;
  data: Blob | ArrayBuffer | ArrayBufferView;
}

export interface UploadFileResponse {
  path: string;
}

export interface DownloadFileResponse {
  path: string;
  data: Uint8Array;
  contentType: string | null;
}

interface RequestOptions {
  body?: BodyInit | object;
  headers?: HeadersInit;
  query?: Record<string, string | number | boolean | undefined>;
}

function toBinaryPayload(data: Blob | ArrayBuffer | ArrayBufferView): BlobPart {
  if (data instanceof Blob) return data;
  if (ArrayBuffer.isView(data)) {
    return new Uint8Array(data.buffer, data.byteOffset, data.byteLength).slice();
  }
  return new Uint8Array(data);
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
    return this.requestJson<SandboxResponse[]>('GET', '/sandboxes');
  }

  createSandbox(payload: CreateSandboxPayload = {}): Promise<SandboxResponse> {
    return this.requestJson<SandboxResponse>('POST', '/sandboxes', { body: payload });
  }

  getSandbox(idOrAlias: string): Promise<SandboxResponse> {
    return this.requestJson<SandboxResponse>('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}`);
  }

  updateSandbox(idOrAlias: string, payload: UpdateSandboxPayload): Promise<SandboxResponse> {
    return this.requestJson<SandboxResponse>('PATCH', `/sandboxes/${encodeURIComponent(idOrAlias)}`, { body: payload });
  }

  async deleteSandbox(idOrAlias: string): Promise<{ ok: true }> {
    await this.requestJson<null>('DELETE', `/sandboxes/${encodeURIComponent(idOrAlias)}`);
    return { ok: true };
  }

  pauseSandbox(idOrAlias: string): Promise<{ ok: boolean }> {
    return this.requestJson<{ ok: boolean }>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/pause`);
  }

  resumeSandbox(idOrAlias: string): Promise<{ ok: boolean }> {
    return this.requestJson<{ ok: boolean }>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/resume`);
  }

  restartBrowser(idOrAlias: string, payload: RestartBrowserPayload = {}): Promise<RestartBrowserResponse> {
    return this.requestJson<RestartBrowserResponse>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/browser/restart`, {
      body: { level: payload.level ?? 'hard' },
    });
  }

  getBrowserInfo(idOrAlias: string): Promise<BrowserInfoResponse> {
    return this.requestJson<BrowserInfoResponse>('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}/browser/info`);
  }

  getBrowserViewport(idOrAlias: string): Promise<BrowserViewportResponse> {
    return this.requestJson<BrowserViewportResponse>('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}/browser/viewport`);
  }

  getBrowserScreenshot(
    idOrAlias: string,
    options: { type?: ScreenshotType; format?: ScreenshotFormat; target_id?: string } = {},
  ): Promise<ScreenshotResponse> {
    return this.requestJson<ScreenshotResponse>('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}/browser/screenshot`, {
      query: {
        ...(options.type ? { type: options.type } : {}),
        ...(options.format ? { format: options.format } : {}),
        ...(options.target_id ? { target_id: options.target_id } : {}),
      },
    });
  }

  executeBrowserActions(idOrAlias: string, payload: BrowserActionsPayload): Promise<BrowserActionsResponse> {
    return this.requestJson<BrowserActionsResponse>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/browser/actions`, { body: payload });
  }

  getCdpInfo(idOrAlias: string): Promise<CdpInfoResponse> {
    return this.requestJson<CdpInfoResponse>('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}/browser/cdp/info`);
  }

  createVncTicket(idOrAlias: string, payload: { mode?: VncTicketMode; ttl_sec?: number } = {}): Promise<VncTicketResponse> {
    return this.requestJson<VncTicketResponse>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/vnc/tickets`, {
      body: {
        mode: payload.mode ?? 'one_time',
        ...(payload.ttl_sec !== undefined ? { ttl_sec: payload.ttl_sec } : {}),
      },
    });
  }

  async getVncUrl(idOrAlias: string): Promise<VncUrlResponse> {
    const sandbox = await this.getSandbox(idOrAlias);
    const ticket = await this.createVncTicket(String(sandbox.id), { mode: 'one_time' });
    return {
      sandbox_id: sandbox.id,
      ...(sandbox.alias !== undefined ? { alias: sandbox.alias } : {}),
      ticket: ticket.ticket,
      url: `${sandbox.browser.vnc_entry_base_url}?ticket=${ticket.ticket}`,
      expires_at: ticket.expires_at,
      mode: ticket.mode,
      ttl_sec: ticket.ttl_sec,
    };
  }

  listFiles(idOrAlias: string, path = '/workspace'): Promise<FileEntry[]> {
    return this.requestJson<FileEntry[]>('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}/files/list`, {
      query: { path },
    });
  }

  readFile(idOrAlias: string, path: string): Promise<ReadFileResponse> {
    return this.requestJson<ReadFileResponse>('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}/files/read`, {
      query: { path },
    });
  }

  writeFile(idOrAlias: string, payload: WriteFilePayload): Promise<WriteFileResponse> {
    return this.requestJson<WriteFileResponse>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/files/write`, {
      body: {
        path: payload.path,
        content: payload.content,
        overwrite: payload.overwrite ?? false,
      },
    });
  }

  uploadFile(idOrAlias: string, payload: UploadFilePayload): Promise<UploadFileResponse> {
    const formData = new FormData();
    formData.set('upload', new Blob([toBinaryPayload(payload.data)]), payload.filename);
    return this.requestJson<UploadFileResponse>('POST', `/sandboxes/${encodeURIComponent(idOrAlias)}/files/upload`, {
      body: formData,
    });
  }

  async downloadFile(idOrAlias: string, path: string): Promise<DownloadFileResponse> {
    const response = await this.requestRaw('GET', `/sandboxes/${encodeURIComponent(idOrAlias)}/files/download`, {
      query: { path },
    });
    return {
      path,
      data: new Uint8Array(await response.arrayBuffer()),
      contentType: response.headers.get('content-type'),
    };
  }

  deleteFile(idOrAlias: string, path: string): Promise<{ ok: boolean }> {
    return this.requestJson<{ ok: boolean }>('DELETE', `/sandboxes/${encodeURIComponent(idOrAlias)}/files`, {
      query: { path },
    });
  }

  private async requestJson<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    const response = await this.requestRaw(method, path, options);
    if (response.status === 204) {
      return null as T;
    }
    const text = await response.text();
    return text ? (JSON.parse(text) as T) : (null as T);
  }

  private async requestRaw(method: string, path: string, options: RequestOptions = {}): Promise<Response> {
    const headers = new Headers(options.headers ?? {});
    headers.set('Authorization', `Bearer ${this.token}`);

    const init: RequestInit = { method, headers };
    if (options.body !== undefined) {
      if (
        typeof options.body === 'string'
        || options.body instanceof Blob
        || options.body instanceof FormData
        || options.body instanceof URLSearchParams
        || options.body instanceof ArrayBuffer
        || ArrayBuffer.isView(options.body)
      ) {
        init.body = options.body as BodyInit;
      } else {
        headers.set('Content-Type', 'application/json');
        init.body = JSON.stringify(options.body);
      }
    }

    const response = await this.fetchImpl(this.buildUrl(path, options.query), init);
    if (response.ok) {
      return response;
    }

    const detail = await this.extractError(response);
    if (response.status === 401) throw new VergeAuthError(detail || 'authentication failed');
    if (response.status === 404) throw new VergeNotFoundError(detail || 'resource not found');
    if (response.status === 409) throw new VergeConflictError(detail || 'request conflict');
    if (response.status === 413) throw new VergeValidationError(detail || 'payload too large');
    if (response.status === 422) throw new VergeValidationError(detail || 'validation failed');
    throw new VergeServerError(`${response.status}: ${detail || 'request failed'}`);
  }

  private buildUrl(path: string, query: RequestOptions['query']): string {
    const url = new URL(`${this.baseUrl}${path}`);
    for (const [key, value] of Object.entries(query ?? {})) {
      if (value === undefined) continue;
      url.searchParams.set(key, String(value));
    }
    return url.toString();
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
