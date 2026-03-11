import { FormEvent, useState } from "react";
import useSWR, { mutate } from "swr";

type Sandbox = {
  id: string;
  alias: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  last_active_at: string;
  width: number;
  height: number;
  metadata: Record<string, unknown>;
  browser: {
    cdp_url: string;
    vnc_entry_base_url: string;
    vnc_ticket_endpoint: string;
    browser_version?: string | null;
    protocol_version?: string | null;
    viewport: { width: number; height: number };
  };
};

const API_URL_KEY = "verge-browser.admin.api-url";
const TOKEN_KEY = "verge-browser.admin.token";
const DEFAULT_API_URL = window.location.origin;

const SWR_CONFIG_KEY = "sandboxes";

async function api<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const baseUrl = localStorage.getItem(API_URL_KEY) || DEFAULT_API_URL;
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers || {}),
    },
  });

  if (response.status === 401) {
    throw new Error("Unauthorized. Check the admin token.");
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      payload?.detail || `Request failed with ${response.status}`,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function useSandboxes(token: string) {
  const { data, error, isLoading, isValidating } = useSWR<Sandbox[]>(
    token ? [SWR_CONFIG_KEY, token] : null,
    ([, t]: [string, string]) => api<Sandbox[]>("/sandboxes", t, { method: "GET" }),
    {
      revalidateOnFocus: true,
      refreshInterval: 30000,
    },
  );

  return {
    sandboxes: data || [],
    error,
    isLoading,
    isValidating,
    refresh: () => mutate([SWR_CONFIG_KEY, token]),
  };
}

function useSandboxDetail(token: string, idOrAlias: string | null) {
  const { data, error, isLoading } = useSWR<Sandbox>(
    token && idOrAlias ? [`${SWR_CONFIG_KEY}/${idOrAlias}`, token, idOrAlias] : null,
    ([, t, id]: [string, string, string]) => api<Sandbox>(`/sandboxes/${id}`, t, { method: "GET" }),
  );

  return {
    detail: data || null,
    error,
    isLoading,
  };
}

export function App() {
  // Saved state (used for API calls)
  const [token, setToken] = useState(localStorage.getItem(TOKEN_KEY) || "");

  // Form input state (separate from saved state)
  const savedToken = localStorage.getItem(TOKEN_KEY) || "";
  const savedApiUrl = localStorage.getItem(API_URL_KEY) || DEFAULT_API_URL;
  const [inputToken, setInputToken] = useState(savedToken);
  const [inputApiUrl, setInputApiUrl] = useState(savedApiUrl);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [createAlias, setCreateAlias] = useState("");
  const [isActionLoading, setIsActionLoading] = useState(false);

  const { sandboxes, isLoading: isListLoading, isValidating, refresh } = useSandboxes(token);
  const { detail: selected } = useSandboxDetail(token, selectedId);

  const error = actionError;

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    localStorage.setItem(TOKEN_KEY, inputToken);
    localStorage.setItem(API_URL_KEY, inputApiUrl);
    setToken(inputToken);
  }

  async function createSandbox() {
    setIsActionLoading(true);
    setActionError("");
    try {
      const detail = await api<Sandbox>("/sandboxes", token, {
        method: "POST",
        body: JSON.stringify({
          alias: createAlias || undefined,
          width: 1280,
          height: 1024,
        }),
      });
      setCreateAlias("");
      await refresh();
      setSelectedId(detail.id);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setIsActionLoading(false);
    }
  }

  async function runAction(
    action: "pause" | "resume" | "delete" | "vnc",
    sandbox: Sandbox,
  ) {
    setIsActionLoading(true);
    setActionError("");
    try {
      if (action === "delete") {
        await api(`/sandboxes/${sandbox.id}`, token, { method: "DELETE" });
        setSelectedId(null);
      } else if (action === "vnc") {
        const ticket = await api<{ ticket: string }>(
          `/sandboxes/${sandbox.id}/vnc/tickets`,
          token,
          {
            method: "POST",
            body: JSON.stringify({ mode: "one_time" }),
          },
        );
        window.open(
          `${sandbox.browser.vnc_entry_base_url}?ticket=${ticket.ticket}`,
          "_blank",
          "noopener,noreferrer",
        );
      } else {
        await api(`/sandboxes/${sandbox.id}/${action}`, token, {
          method: "POST",
        });
      }
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setIsActionLoading(false);
    }
  }

  function logout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setInputToken("");
    setSelectedId(null);
  }

  if (!token) {
    return (
      <main className="shell login-shell">
        <section className="login-card">
          <p className="eyebrow">Verge Browser</p>
          <h1>Admin Console</h1>
          <p className="muted">
            Use the shared admin token to manage every sandbox on this control
            plane.
          </p>
          <form onSubmit={handleLogin} className="stack">
            <label>
              API URL
              <input
                value={inputApiUrl}
                onChange={(event) => setInputApiUrl(event.target.value)}
                placeholder={DEFAULT_API_URL}
              />
            </label>
            <label>
              Admin Token
              <input
                value={inputToken}
                onChange={(event) => setInputToken(event.target.value)}
                placeholder="Bearer token value"
                type="password"
              />
            </label>
            <button type="submit">Open Console</button>
          </form>
          {error ? <p className="error">{error}</p> : null}
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <section className="toolbar">
        <div>
          <p className="eyebrow">Connected</p>
          <h1>Sandbox Control</h1>
        </div>
        <div className="toolbar-actions">
          <input
            value={createAlias}
            onChange={(event) => setCreateAlias(event.target.value)}
            placeholder="alias (optional)"
          />
          <button className="create-btn" onClick={() => void createSandbox()} disabled={isActionLoading}>
            {isActionLoading ? "Creating..." : "Create Sandbox"}
          </button>
          <button className="ghost" onClick={() => void refresh()}>
            Refresh
          </button>
          <button className="ghost" onClick={logout}>
            Logout
          </button>
        </div>
      </section>

      {error ? <p className="error banner">{error}</p> : null}

      <section className="grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Sandboxes</h2>
            <span>{isListLoading || isValidating ? "Syncing..." : `${sandboxes.length} total`}</span>
          </div>
          <div className="list">
            {sandboxes.map((sandbox) => (
              <button
                key={sandbox.id}
                className={`list-item ${selectedId === sandbox.id ? "active" : ""}`}
                onClick={() => setSelectedId(sandbox.id)}
              >
                <strong>{sandbox.alias || sandbox.id}</strong>
                <span>{sandbox.id}</span>
                <span>{sandbox.status}</span>
              </button>
            ))}
            {!sandboxes.length ? (
              <p className="muted">No sandboxes yet.</p>
            ) : null}
          </div>
        </article>

        <article className="panel detail-panel">
          {selected ? (
            <>
              <div className="panel-header">
                <div>
                  <h2>{selected.alias || selected.id}</h2>
                  <p className="muted">{selected.id}</p>
                </div>
                <span
                  className={`status status-${selected.status.toLowerCase()}`}
                >
                  {selected.status}
                </span>
              </div>

              <div className="detail-grid">
                <div>
                  <label>Viewport</label>
                  <p>
                    {selected.width} x {selected.height}
                  </p>
                </div>
                <div>
                  <label>Created</label>
                  <p>{new Date(selected.created_at).toLocaleString()}</p>
                </div>
                <div>
                  <label>Updated</label>
                  <p>{new Date(selected.updated_at).toLocaleString()}</p>
                </div>
                <div>
                  <label>CDP</label>
                  <p className="mono">{selected.browser.cdp_url}</p>
                </div>
              </div>

              <div className="action-row">
                <button onClick={() => void runAction("pause", selected)} disabled={isActionLoading}>
                  Pause
                </button>
                <button onClick={() => void runAction("resume", selected)} disabled={isActionLoading}>
                  Resume
                </button>
                <button onClick={() => void runAction("vnc", selected)} disabled={isActionLoading}>
                  Open VNC
                </button>
                <button
                  className="danger"
                  onClick={() => void runAction("delete", selected)}
                  disabled={isActionLoading}
                >
                  Delete
                </button>
              </div>

              <div className="metadata">
                <label>Metadata</label>
                <pre>{JSON.stringify(selected.metadata, null, 2)}</pre>
              </div>
            </>
          ) : (
            <div className="empty-state">
              <p className="eyebrow">Details</p>
              <h2>Select a sandbox</h2>
              <p className="muted">
                The right panel shows CDP, timestamps and action entry points
                for the selected sandbox.
              </p>
            </div>
          )}
        </article>
      </section>
    </main>
  );
}
