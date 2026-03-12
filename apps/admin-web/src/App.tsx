import { FormEvent, useState } from "react";
import useSWR, { mutate } from "swr";
import { toast } from "sonner";

// GitHub Icon Component
function GitHubIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      width="20"
      height="20"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.17 6.839 9.49.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.604-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.464-1.11-1.464-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.167 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
    </svg>
  );
}

type Sandbox = {
  id: string;
  alias: string | null;
  kind: "xvfb_vnc" | "xpra";
  status: string;
  created_at: string;
  updated_at: string;
  last_active_at: string;
  width: number;
  height: number;
  metadata: Record<string, unknown>;
  browser: {
    browser_version?: string | null;
    protocol_version?: string | null;
    web_socket_debugger_url_present: boolean;
    viewport: { width: number; height: number };
  };
};

type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

function canPause(status: string) {
  return status !== "STOPPED";
}

function canResume(status: string) {
  return status === "STOPPED" || status === "FAILED";
}

function canOpenSession(status: string) {
  return status === "RUNNING" || status === "DEGRADED";
}

function actionHint(status: string) {
  if (status === "STARTING") {
    return "Starting sandboxes can be paused or deleted. Session and CDP become available after readiness completes.";
  }
  if (status === "STOPPED") {
    return "Stopped sandboxes must be resumed before session or CDP access.";
  }
  if (status === "FAILED") {
    return "Failed sandboxes can be resumed or deleted. Session and CDP are unavailable until recovery.";
  }
  return null;
}

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
    const message = "Unauthorized. Check the admin token.";
    toast.error(message);
    throw new Error(message);
  }
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as {
      message?: string;
      detail?: string;
    } | null;
    const message =
      payload?.message ||
      payload?.detail ||
      `Request failed with ${response.status}`;
    toast.error(message);
    throw new Error(message);
  }
  const payload = (await response.json()) as ApiEnvelope<T> | T;
  if (
    payload &&
    typeof payload === "object" &&
    "code" in payload &&
    "message" in payload &&
    "data" in payload
  ) {
    return payload.data;
  }
  return payload as T;
}

function useSandboxes(token: string) {
  const { data, error, isLoading, isValidating } = useSWR<Sandbox[]>(
    token ? [SWR_CONFIG_KEY, token] : null,
    ([, t]: [string, string]) =>
      api<Sandbox[]>("/sandbox", t, { method: "GET" }),
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
    token && idOrAlias
      ? [`${SWR_CONFIG_KEY}/${idOrAlias}`, token, idOrAlias]
      : null,
    ([, t, id]: [string, string, string]) =>
      api<Sandbox>(`/sandbox/${id}`, t, { method: "GET" }),
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
  const [createAlias, setCreateAlias] = useState("");
  const [createKind, setCreateKind] = useState<"xvfb_vnc" | "xpra">("xvfb_vnc");
  const [isActionLoading, setIsActionLoading] = useState(false);

  const {
    sandboxes,
    isLoading: isListLoading,
    isValidating,
    refresh,
  } = useSandboxes(token);
  const { detail: selected } = useSandboxDetail(token, selectedId);
  const selectedStatus = selected?.status ?? null;
  const canPauseSelected = selectedStatus ? canPause(selectedStatus) : false;
  const canResumeSelected = selectedStatus ? canResume(selectedStatus) : false;
  const canOpenSessionSelected = selectedStatus
    ? canOpenSession(selectedStatus)
    : false;
  const selectedActionHint = selectedStatus ? actionHint(selectedStatus) : null;

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    localStorage.setItem(TOKEN_KEY, inputToken);
    localStorage.setItem(API_URL_KEY, inputApiUrl);
    setToken(inputToken);
  }

  async function createSandbox() {
    setIsActionLoading(true);
    try {
      const detail = await api<Sandbox>("/sandbox", token, {
        method: "POST",
        body: JSON.stringify({
          alias: createAlias || undefined,
          kind: createKind,
          width: 1280,
          height: 1024,
        }),
      });
      setCreateAlias("");
      await refresh();
      setSelectedId(detail.id);
      toast.success(
        `Sandbox ${detail.alias || detail.id.slice(0, 8)} created successfully`,
      );
    } catch {
      // Error is already toasted by api()
    } finally {
      setIsActionLoading(false);
    }
  }

  async function runAction(
    action: "pause" | "resume" | "delete" | "session" | "cdp",
    sandbox: Sandbox,
  ) {
    setIsActionLoading(true);
    try {
      if (action === "delete") {
        await api(`/sandbox/${sandbox.id}`, token, { method: "DELETE" });
        setSelectedId(null);
        toast.success("Sandbox deleted successfully");
      } else if (action === "session") {
        const ticket = await api<{ ticket: string; session_url: string }>(
          `/sandbox/${sandbox.id}/session/apply`,
          token,
          {
            method: "POST",
            body: JSON.stringify({ mode: "permanent" }),
          },
        );
        window.open(ticket.session_url, "_blank", "noopener,noreferrer");
        toast.success("Session opened");
      } else if (action === "cdp") {
        const ticket = await api<{ ticket: string; cdp_url: string }>(
          `/sandbox/${sandbox.id}/cdp/apply`,
          token,
          {
            method: "POST",
            body: JSON.stringify({ mode: "reusable" }),
          },
        );
        await navigator.clipboard.writeText(ticket.cdp_url);
        toast.success("CDP URL copied to clipboard");
      } else {
        await api(`/sandbox/${sandbox.id}/${action}`, token, {
          method: "POST",
        });
        toast.success(`Sandbox ${action}d successfully`);
      }
      await refresh();
    } catch {
      // Error is already toasted by api()
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
          <p className="eyebrow">Welcome to Verge Browser</p>
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
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <section className="toolbar">
        <div>
          <p className="eyebrow">
            <span>Verge Browser</span>
          </p>
          <h1>Sandbox Control</h1>
        </div>
              <div className="toolbar-actions">
                <input
                  value={createAlias}
                  onChange={(event) => setCreateAlias(event.target.value)}
                  placeholder="alias (optional)"
                />
                <select
                  value={createKind}
                  onChange={(event) =>
                    setCreateKind(event.target.value as "xvfb_vnc" | "xpra")
                  }
                >
                  <option value="xvfb_vnc">xvfb + vnc</option>
                  <option value="xpra">xpra</option>
                </select>
                <button
            className="create-btn"
            onClick={() => void createSandbox()}
            disabled={isActionLoading}
          >
            {isActionLoading ? "Creating..." : "Create Sandbox"}
          </button>
          <button className="ghost" onClick={() => void refresh()}>
            Refresh
          </button>
          <button className="ghost" onClick={logout}>
            Logout
          </button>
          <a
            href="https://github.com/zzzgydi/verge-browser"
            target="_blank"
            rel="noopener noreferrer"
            className="github-link"
            title="View on GitHub"
          >
            <GitHubIcon />
          </a>
        </div>
      </section>

      <section className="grid">
        <article className="panel">
          <div className="panel-header">
            <h2>Sandboxes</h2>
            <span>
              {isListLoading || isValidating
                ? "Syncing..."
                : `${sandboxes.length} total`}
            </span>
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
                      <label>Kind</label>
                      <p>{selected.kind}</p>
                    </div>
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
              </div>

              <div className="action-row">
                <button
                  onClick={() => void runAction("pause", selected)}
                  disabled={isActionLoading || !canPauseSelected}
                >
                  Pause
                </button>
                <button
                  onClick={() => void runAction("resume", selected)}
                  disabled={isActionLoading || !canResumeSelected}
                >
                  Resume
                </button>
                <button
                  onClick={() => void runAction("session", selected)}
                  disabled={isActionLoading || !canOpenSessionSelected}
                >
                  Open Session
                </button>
                <button
                  onClick={() => void runAction("cdp", selected)}
                  disabled={isActionLoading || !canOpenSessionSelected}
                >
                  Connect CDP
                </button>
                <button
                  className="danger"
                  onClick={() => void runAction("delete", selected)}
                  disabled={isActionLoading}
                >
                  Delete
                </button>
              </div>
              {selectedActionHint ? (
                <p className="muted">{selectedActionHint}</p>
              ) : null}

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
