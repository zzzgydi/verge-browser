import { FormEvent, useEffect, useState } from "react";
import useSWR, { mutate } from "swr";
import { toast } from "sonner";

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

function Icon({
  name,
}: {
  name:
    | "plus"
    | "refresh"
    | "external"
    | "code"
    | "browser"
    | "search"
    | "logout";
}) {
  const paths = {
    plus: "M12 5v14M5 12h14",
    refresh:
      "M20 7v5h-5M4 17v-5h5M6.1 7a7 7 0 0 1 11.6-1L20 9M4 15l2.3 3A7 7 0 0 0 17.9 17",
    external:
      "M14 4h6v6M20 4l-9 9M10 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5",
    code: "m8 7-5 5 5 5m8-10 5 5-5 5M14 4l-4 16",
    browser:
      "M4 4h16a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1ZM3 9h18M7 6.5h.01M10 6.5h.01",
    search: "M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13Zm5-1.5L21 21",
    logout: "M9 4H4v16h5M9 12h12m-5-5 5 5-5 5",
  };
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}

function Status({ value }: { value: string }) {
  const icons: Record<string, string> = {
    RUNNING: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM10 8l6 4-6 4Z",
    STOPPED: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9 8v8M15 8v8",
    STARTING: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 7v5l3 2",
    DEGRADED: "M12 3 2 21h20ZM12 9v5M12 17h.01",
    FAILED: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM9 9l6 6M15 9l-6 6",
  };
  return (
    <span className={`status status-${value.toLowerCase()}`}>
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path
          d={icons[value] ?? "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM8 12h8"}
        />
      </svg>
      {value.toLowerCase()}
    </span>
  );
}

type Sandbox = {
  id: string;
  alias: string | null;
  kind: "xvfb_vnc" | "xpra";
  browser_engine: "chromium" | "cloakbrowser";
  status: string;
  created_at: string;
  updated_at: string;
  last_active_at: string;
  width: number;
  height: number;
  enable_gpu: boolean;
  metadata: Record<string, unknown>;
  browser: {
    browser_version?: string | null;
    protocol_version?: string | null;
    web_socket_debugger_url_present: boolean;
    viewport: { width: number; height: number };
  };
};

type EngineAvailability = {
  browser_engine: Sandbox["browser_engine"];
  available: boolean;
  reason: string | null;
  kinds: Sandbox["kind"][];
};

type ApiEnvelope<T> = {
  code: number;
  message: string;
  data: T;
};

type AccessTicketMode = "one_time" | "reusable" | "permanent";

type AccessPreset = {
  key: string;
  label: string;
  mode: AccessTicketMode;
  ttlSec?: number;
};

const ACCESS_PRESETS: AccessPreset[] = [
  { key: "one_time_60", label: "1 min", mode: "one_time", ttlSec: 60 },
  { key: "reusable_300", label: "5 min", mode: "reusable", ttlSec: 300 },
  { key: "reusable_900", label: "15 min", mode: "reusable", ttlSec: 900 },
  { key: "reusable_3600", label: "1 hour", mode: "reusable", ttlSec: 3600 },
  { key: "permanent", label: "Permanent", mode: "permanent" },
];

const DEFAULT_SESSION_PRESET_KEY = "reusable_900";
const DEFAULT_CDP_PRESET_KEY = "reusable_300";

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
    throw new Error("Unauthorized. Check the admin token.");
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
  const {
    data,
    error,
    isLoading,
    mutate: refresh,
  } = useSWR<Sandbox>(
    token && idOrAlias
      ? [`${SWR_CONFIG_KEY}/${idOrAlias}`, token, idOrAlias]
      : null,
    ([, t, id]: [string, string, string]) =>
      api<Sandbox>(`/sandbox/${id}`, t, { method: "GET" }),
    { refreshInterval: 30000 },
  );

  return {
    detail: data || null,
    error,
    isLoading,
    refresh,
  };
}

function ScreenshotPreview({
  token,
  sandbox,
}: {
  token: string;
  sandbox: Sandbox;
}) {
  const [capture, setCapture] = useState<{
    src: string;
    capturedAt: Date;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const available = canOpenSession(sandbox.status);

  useEffect(() => {
    if (!available) return;
    // Each selection owns its request; switching sandboxes discards late responses.
    const controller = new AbortController();
    let active = true;
    const timeout = window.setTimeout(() => controller.abort(), 20000);
    setIsLoading(true);
    setError(null);

    void api<{ media_type: string; data_base64: string }>(
      `/sandbox/${sandbox.id}/browser/screenshot`,
      token,
      {
        method: "POST",
        body: JSON.stringify({ type: "window", format: "png" }),
        signal: controller.signal,
        cache: "no-store",
      },
    )
      .then((image) => {
        if (!active) return;
        if (
          image.media_type !== "image/png" ||
          typeof image.data_base64 !== "string" ||
          !image.data_base64
        ) {
          throw new Error(
            "The server returned an invalid screenshot. Try again.",
          );
        }
        setCapture({
          src: `data:image/png;base64,${image.data_base64}`,
          capturedAt: new Date(),
        });
      })
      .catch((error: unknown) => {
        if (!active) return;
        setError(
          controller.signal.aborted
            ? "Screenshot timed out. Try again."
            : error instanceof Error
              ? error.message
              : "Could not capture screenshot. Try again.",
        );
      })
      .finally(() => {
        window.clearTimeout(timeout);
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [token, sandbox.id, available, revision]);

  return (
    <section
      className="screenshot-preview"
      aria-labelledby="screenshot-heading"
    >
      <div className="screenshot-heading">
        <h3 id="screenshot-heading">Screenshot</h3>
        {available ? (
          <button
            className="ghost"
            onClick={() => setRevision((value) => value + 1)}
            disabled={isLoading}
            aria-label="Refresh screenshot"
          >
            <Icon name="refresh" />
            {isLoading ? "Capturing..." : "Refresh"}
          </button>
        ) : null}
      </div>
      {!available ? (
        <p className="muted screenshot-unavailable">
          {sandbox.status === "STOPPED"
            ? "Resume this sandbox to preview its browser."
            : "A screenshot will be available when the browser is ready."}
        </p>
      ) : (
        <>
          <div className="screenshot-frame" aria-busy={isLoading}>
            {capture ? (
              <img
                src={capture.src}
                alt={`Browser screenshot of ${sandbox.alias || sandbox.id}`}
                onError={() => {
                  setCapture(null);
                  setError("Could not display the screenshot. Try again.");
                }}
              />
            ) : (
              <p className="muted" role={isLoading ? "status" : undefined}>
                {isLoading
                  ? "Capturing browser window..."
                  : "No screenshot available"}
              </p>
            )}
          </div>
          {error ? (
            <p className="error-text screenshot-message" role="alert">
              {error}
            </p>
          ) : null}
          {capture ? (
            <p className="muted screenshot-message">
              {error ? "Last successful capture" : "Captured"} at{" "}
              <time dateTime={capture.capturedAt.toISOString()}>
                {capture.capturedAt.toLocaleTimeString()}
              </time>
            </p>
          ) : null}
        </>
      )}
    </section>
  );
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
  const [createEngine, setCreateEngine] =
    useState<Sandbox["browser_engine"]>("chromium");
  const [createResolution, setCreateResolution] = useState("1280x1024");
  const [createEnableGpu, setCreateEnableGpu] = useState(false);
  const [sessionPresetKey, setSessionPresetKey] = useState(
    DEFAULT_SESSION_PRESET_KEY,
  );
  const [cdpPresetKey, setCdpPresetKey] = useState(DEFAULT_CDP_PRESET_KEY);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const isActionLoading = pendingAction !== null;

  const {
    sandboxes,
    isLoading: isListLoading,
    isValidating,
    error: listError,
    refresh,
  } = useSandboxes(token);
  const {
    data: engines,
    error: enginesError,
    mutate: refreshEngines,
  } = useSWR<EngineAvailability[]>(
    token ? ["browser-engines", token] : null,
    ([, t]: [string, string]) =>
      api<EngineAvailability[]>("/runtime/engines", t),
    { refreshInterval: 30000 },
  );
  const cloak = engines?.find(
    (engine) => engine.browser_engine === "cloakbrowser",
  );
  const createKinds =
    createEngine === "cloakbrowser"
      ? (cloak?.kinds ?? [])
      : ["xvfb_vnc", "xpra"];
  const {
    detail: selected,
    error: detailError,
    isLoading: isDetailLoading,
    refresh: refreshDetail,
  } = useSandboxDetail(token, selectedId);
  const visibleSandboxes = sandboxes.filter((sandbox) =>
    `${sandbox.alias ?? ""} ${sandbox.id} ${sandbox.browser_engine} ${sandbox.status}`
      .toLowerCase()
      .includes(search.trim().toLowerCase()),
  );
  const selectedStatus = selected?.status ?? null;
  const canPauseSelected = selectedStatus ? canPause(selectedStatus) : false;
  const canResumeSelected = selectedStatus ? canResume(selectedStatus) : false;
  const canOpenSessionSelected = selectedStatus
    ? canOpenSession(selectedStatus)
    : false;
  const selectedActionHint = selectedStatus ? actionHint(selectedStatus) : null;
  const sessionPreset =
    ACCESS_PRESETS.find((preset) => preset.key === sessionPresetKey) ??
    ACCESS_PRESETS[0];
  const cdpPreset =
    ACCESS_PRESETS.find((preset) => preset.key === cdpPresetKey) ??
    ACCESS_PRESETS[0];

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    localStorage.setItem(TOKEN_KEY, inputToken);
    localStorage.setItem(API_URL_KEY, inputApiUrl.trim().replace(/\/+$/, ""));
    setToken(inputToken);
  }

  async function createSandbox() {
    setPendingAction("create");
    try {
      const [resW, resH] = createResolution.split("x").map(Number);
      const detail = await api<Sandbox>("/sandbox", token, {
        method: "POST",
        body: JSON.stringify({
          alias: createAlias || undefined,
          kind: createKind,
          browser_engine: createEngine,
          width: resW,
          height: resH,
          enable_gpu: createEnableGpu,
        }),
      });
      setCreateAlias("");
      await refresh();
      setSelectedId(detail.id);
      if (detail.status === "FAILED" || detail.status === "DEGRADED") {
        toast.error(
          String(
            detail.metadata.runtime_error ||
              "Sandbox did not become ready. Inspect its details.",
          ),
        );
      } else {
        toast.success(
          `Sandbox ${detail.alias || detail.id.slice(0, 8)} created successfully`,
        );
      }
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Could not create sandbox. Try again.",
      );
    } finally {
      setPendingAction(null);
    }
  }

  async function runAction(
    action: "pause" | "resume" | "delete" | "session" | "cdp",
    sandbox: Sandbox,
  ) {
    setPendingAction(action);
    let sessionWindow: Window | null = null;
    try {
      if (action === "delete") {
        await api(`/sandbox/${sandbox.id}`, token, { method: "DELETE" });
        toast.success("Sandbox deleted successfully");
        const remaining = sandboxes.filter((s) => s.id !== sandbox.id);
        setSelectedId(remaining[0]?.id ?? null);
      } else if (action === "session") {
        sessionWindow = window.open("", "_blank");
        if (!sessionWindow) {
          throw new Error(
            "Popup blocked. Allow popups for this site and retry.",
          );
        }
        sessionWindow.opener = null;
        sessionWindow.document.title = "Opening session...";
        sessionWindow.document.body.innerHTML =
          '<p style="font-family: sans-serif; padding: 16px;">Opening session...</p>';
        const ticket = await api<{ ticket: string; session_url: string }>(
          `/sandbox/${sandbox.id}/session/apply`,
          token,
          {
            method: "POST",
            body: JSON.stringify({
              mode: sessionPreset.mode,
              ...(sessionPreset.ttlSec !== undefined
                ? { ttl_sec: sessionPreset.ttlSec }
                : {}),
            }),
          },
        );
        sessionWindow.location.replace(ticket.session_url);
        toast.success("Session opened");
      } else if (action === "cdp") {
        const ticket = await api<{ ticket: string; cdp_url: string }>(
          `/sandbox/${sandbox.id}/cdp/apply`,
          token,
          {
            method: "POST",
            body: JSON.stringify({
              mode: cdpPreset.mode,
              ...(cdpPreset.ttlSec !== undefined
                ? { ttl_sec: cdpPreset.ttlSec }
                : {}),
            }),
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
      if (action !== "delete") await refreshDetail();
    } catch (error) {
      sessionWindow?.close();
      toast.error(
        error instanceof Error ? error.message : "Action failed. Try again.",
      );
    } finally {
      setPendingAction(null);
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
      <main className="login-shell">
        <section className="login-card">
          <div className="brand">
            <Icon name="browser" />
            <span>Verge Browser</span>
          </div>
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
                type="url"
                required
              />
            </label>
            <label>
              Admin Token
              <input
                value={inputToken}
                onChange={(event) => setInputToken(event.target.value)}
                placeholder="Bearer token value"
                type="password"
                required
              />
            </label>
            <button type="submit">
              Open Console <Icon name="external" />
            </button>
          </form>
        </section>
      </main>
    );
  }

  return (
    <div className="shell">
      <a className="skip-link" href="#sandbox-workspace">
        Skip to sandboxes
      </a>
      <header className="topbar">
        <div className="console-heading">
          <Icon name="browser" />
          <h1>Verge Browser</h1>
        </div>
        <nav className="toolbar-actions" aria-label="Console actions">
          <button
            className="ghost"
            aria-label={isValidating ? "Syncing..." : "Refresh"}
            title="Refresh now (automatically refreshes every 30 seconds)"
            onClick={() => {
              void refresh();
              void refreshEngines();
              void refreshDetail();
            }}
            disabled={isValidating}
          >
            <Icon name="refresh" />
            <span>{isValidating ? "Syncing..." : "Refresh"}</span>
          </button>
          <button
            className="ghost"
            onClick={logout}
            aria-label="Logout"
            title="Logout"
          >
            <Icon name="logout" />
            <span>Logout</span>
          </button>
          <a
            href="https://github.com/zzzgydi/verge-browser"
            target="_blank"
            rel="noopener noreferrer"
            className="github-link"
            aria-label="View on GitHub"
            title="View on GitHub"
          >
            <GitHubIcon />
          </a>
        </nav>
      </header>

      <main>
        <section className="create-panel" aria-labelledby="create-heading">
          <h2 id="create-heading">Create a sandbox</h2>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void createSandbox();
            }}
          >
            <fieldset className="create-fields" disabled={isActionLoading}>
              <label className="alias-field">
                <span>
                  Alias <span className="optional">(optional)</span>
                </span>
                <input
                  value={createAlias}
                  onChange={(event) => setCreateAlias(event.target.value)}
                  placeholder="e.g. research-browser"
                />
              </label>
              <label>
                Browser engine
                <select
                  value={createEngine}
                  onChange={(event) => {
                    const engine = event.target
                      .value as Sandbox["browser_engine"];
                    setCreateEngine(engine);
                    if (engine === "cloakbrowser") {
                      if (!cloak?.kinds.includes(createKind))
                        setCreateKind(cloak?.kinds[0] ?? "xvfb_vnc");
                      setCreateEnableGpu(false);
                    }
                  }}
                >
                  <option value="chromium">Chromium</option>
                  <option value="cloakbrowser" disabled={!cloak?.available}>
                    CloakBrowser{cloak?.available ? "" : " (not configured)"}
                  </option>
                </select>
              </label>
              <label>
                Desktop runtime
                <select
                  value={createKind}
                  onChange={(event) =>
                    setCreateKind(event.target.value as Sandbox["kind"])
                  }
                >
                  <option
                    value="xvfb_vnc"
                    disabled={!createKinds.includes("xvfb_vnc")}
                  >
                    Xvfb + VNC
                  </option>
                  <option value="xpra" disabled={!createKinds.includes("xpra")}>
                    Xpra
                  </option>
                </select>
              </label>
              <label>
                Resolution
                <select
                  value={createResolution}
                  onChange={(event) => setCreateResolution(event.target.value)}
                >
                  <option value="1280x1024">1280 x 1024</option>
                  <option value="1366x768">1366 x 768</option>
                  <option value="1440x900">1440 x 900</option>
                  <option value="1920x1080">1920 x 1080</option>
                  <option value="2560x1440">2560 x 1440</option>
                </select>
              </label>
              <label className="gpu-field">
                <span>Acceleration</span>
                <span className="checkbox-control">
                  <input
                    type="checkbox"
                    checked={createEnableGpu}
                    disabled={createEngine === "cloakbrowser"}
                    onChange={(event) =>
                      setCreateEnableGpu(event.target.checked)
                    }
                  />
                  <span>Enable GPU</span>
                </span>
              </label>
              <button
                className="create-btn"
                type="submit"
                disabled={
                  isActionLoading ||
                  !createKinds.includes(createKind) ||
                  (createEngine === "cloakbrowser" && !cloak?.available)
                }
              >
                <Icon name="plus" />
                {pendingAction === "create" ? "Creating..." : "Create Sandbox"}
              </button>
            </fieldset>
          </form>
          {enginesError ? (
            <p className="engine-hint error-text" role="alert">
              Could not check browser availability. Refresh to try again.
            </p>
          ) : null}
          {cloak && !cloak.available ? (
            <p className="muted engine-hint">{cloak.reason}</p>
          ) : null}
          {createEngine === "cloakbrowser" ? (
            <p className="muted engine-hint">
              Free keys support one running browser at a time. Pause it before
              creating another.
            </p>
          ) : null}
          {createEngine === "cloakbrowser" && createKind === "xpra" ? (
            <p className="muted engine-hint">
              The Cloak Xpra adapter is experimental; real-runtime validation is
              still required.
            </p>
          ) : null}
        </section>

        <section
          className="workspace"
          id="sandbox-workspace"
          aria-label="Sandbox workspace"
          tabIndex={-1}
        >
          <aside className="inventory" aria-labelledby="sandboxes-heading">
            <div className="inventory-heading">
              <h2 id="sandboxes-heading">
                Sandboxes <span className="count">{sandboxes.length}</span>
              </h2>
            </div>
            <div className="search-field">
              <Icon name="search" />
              <input
                aria-label="Search sandboxes"
                placeholder="Search name, ID or status"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                type="search"
              />
            </div>
            {listError ? (
              <div className="list-notice error-text" role="alert">
                <strong>Could not load sandboxes</strong>
                <p>{listError.message}</p>
                <button className="ghost" onClick={() => void refresh()}>
                  Try again
                </button>
              </div>
            ) : null}
            <div className="sandbox-list" aria-busy={isListLoading}>
              {isListLoading ? (
                <div className="loading-state" role="status">
                  <p>Loading sandboxes...</p>
                  <div className="skeleton" />
                  <div className="skeleton" />
                  <div className="skeleton" />
                </div>
              ) : (
                visibleSandboxes.map((sandbox) => (
                  <button
                    key={sandbox.id}
                    className={`list-item ${selectedId === sandbox.id ? "active" : ""}`}
                    onClick={() => setSelectedId(sandbox.id)}
                    aria-pressed={selectedId === sandbox.id}
                  >
                    <span className="list-item-title">
                      <strong>{sandbox.alias || sandbox.id}</strong>
                      <Status value={sandbox.status} />
                    </span>
                    {sandbox.alias ? (
                      <span className="mono sandbox-id">{sandbox.id}</span>
                    ) : null}
                    <span className="list-item-meta">
                      <span>
                        {sandbox.browser_engine === "cloakbrowser"
                          ? "CloakBrowser"
                          : "Chromium"}
                      </span>
                      <span>
                        {sandbox.kind === "xpra" ? "Xpra" : "Xvfb + VNC"}
                      </span>
                    </span>
                  </button>
                ))
              )}
              {!isListLoading && !listError && !visibleSandboxes.length ? (
                <div className="list-notice">
                  <strong>
                    {search ? "No matching sandboxes" : "No sandboxes yet"}
                  </strong>
                  <p>
                    {search
                      ? "Try another name, ID or status."
                      : "Create a sandbox to get started."}
                  </p>
                  {search ? (
                    <button className="ghost" onClick={() => setSearch("")}>
                      Clear search
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          </aside>

          <article
            className="detail-panel"
            aria-label="Sandbox details"
            aria-busy={isDetailLoading}
          >
            {selected ? (
              <>
                <header className="detail-header">
                  <div className="header-info">
                    <div className="detail-title">
                      <h2>{selected.alias || selected.id}</h2>
                      <Status value={selected.status} />
                    </div>
                    {selected.alias ? (
                      <p className="mono muted">{selected.id}</p>
                    ) : null}
                  </div>
                  <div
                    className="lifecycle-actions"
                    aria-label="Sandbox lifecycle"
                  >
                    <button
                      className="ghost"
                      onClick={() => void runAction("pause", selected)}
                      disabled={isActionLoading || !canPauseSelected}
                    >
                      {pendingAction === "pause" ? "Pausing..." : "Pause"}
                    </button>
                    <button
                      className="ghost"
                      onClick={() => void runAction("resume", selected)}
                      disabled={isActionLoading || !canResumeSelected}
                    >
                      {pendingAction === "resume" ? "Resuming..." : "Resume"}
                    </button>
                    <button
                      className="danger"
                      onClick={() => void runAction("delete", selected)}
                      disabled={isActionLoading}
                    >
                      {pendingAction === "delete" ? "Deleting..." : "Delete"}
                    </button>
                  </div>
                </header>
                {detailError ? (
                  <p className="error-text" role="alert">
                    Could not refresh these details. Showing the last loaded
                    state. Use Refresh to retry.
                  </p>
                ) : null}
                {selected.metadata.runtime_error ? (
                  <p className="action-hint error-text" role="alert">
                    {String(selected.metadata.runtime_error)}
                  </p>
                ) : null}
                <ScreenshotPreview
                  key={`${selected.id}:${selected.status}`}
                  token={token}
                  sandbox={selected}
                />
                <dl className="detail-grid">
                  <div>
                    <dt>Browser engine</dt>
                    <dd>
                      {selected.browser_engine === "cloakbrowser"
                        ? "CloakBrowser"
                        : "Chromium"}
                    </dd>
                  </div>
                  <div>
                    <dt>Desktop runtime</dt>
                    <dd>{selected.kind === "xpra" ? "Xpra" : "Xvfb + VNC"}</dd>
                  </div>
                  <div>
                    <dt>Viewport</dt>
                    <dd className="numeric">
                      {selected.width} x {selected.height}
                    </dd>
                  </div>
                  <div>
                    <dt>GPU acceleration</dt>
                    <dd>{selected.enable_gpu ? "Enabled" : "Disabled"}</dd>
                  </div>
                  <div>
                    <dt>Created</dt>
                    <dd className="numeric">
                      {new Date(selected.created_at).toLocaleString()}
                    </dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd className="numeric">
                      {new Date(selected.updated_at).toLocaleString()}
                    </dd>
                  </div>
                </dl>

                <section
                  className="connections"
                  aria-labelledby="connections-heading"
                >
                  <h3 id="connections-heading">Connect</h3>
                  <div className="connection-row">
                    <div className="connection-description">
                      <Icon name="browser" />
                      <div>
                        <h4>Browser session</h4>
                        <p>Open the desktop in a new tab.</p>
                      </div>
                    </div>
                    <div className="connection-actions">
                      <label>
                        <span>Link expiry</span>
                        <select
                          aria-label="Session link expiry"
                          value={sessionPresetKey}
                          onChange={(event) =>
                            setSessionPresetKey(event.target.value)
                          }
                          disabled={isActionLoading}
                        >
                          {ACCESS_PRESETS.map((preset) => (
                            <option key={preset.key} value={preset.key}>
                              {preset.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        onClick={() => void runAction("session", selected)}
                        disabled={isActionLoading || !canOpenSessionSelected}
                      >
                        {pendingAction === "session"
                          ? "Opening..."
                          : "Open Session"}
                        <Icon name="external" />
                      </button>
                    </div>
                  </div>
                  <div className="connection-row">
                    <div className="connection-description">
                      <Icon name="code" />
                      <div>
                        <h4>Chrome DevTools Protocol</h4>
                        <p>Copy a URL for your automation client.</p>
                      </div>
                    </div>
                    <div className="connection-actions">
                      <label>
                        <span>Link expiry</span>
                        <select
                          aria-label="CDP link expiry"
                          value={cdpPresetKey}
                          onChange={(event) =>
                            setCdpPresetKey(event.target.value)
                          }
                          disabled={isActionLoading}
                        >
                          {ACCESS_PRESETS.map((preset) => (
                            <option key={preset.key} value={preset.key}>
                              {preset.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button
                        className="ghost"
                        onClick={() => void runAction("cdp", selected)}
                        disabled={isActionLoading || !canOpenSessionSelected}
                      >
                        {pendingAction === "cdp" ? "Copying..." : "Connect CDP"}
                        <Icon name="code" />
                      </button>
                    </div>
                  </div>
                  {selectedActionHint ? (
                    <p className="action-hint">{selectedActionHint}</p>
                  ) : null}
                </section>

                <details className="metadata" key={selected.id}>
                  <summary>
                    Metadata <span>JSON</span>
                  </summary>
                  <pre>{JSON.stringify(selected.metadata, null, 2)}</pre>
                </details>
              </>
            ) : isDetailLoading ? (
              <div className="loading-state detail-loading" role="status">
                <p>Loading sandbox details...</p>
                <div className="skeleton" />
                <div className="skeleton" />
                <div className="skeleton" />
              </div>
            ) : detailError ? (
              <div className="empty-state" role="alert">
                <h2>Could not load this sandbox</h2>
                <p>{detailError.message}</p>
                <button className="ghost" onClick={() => void refreshDetail()}>
                  Try again
                </button>
              </div>
            ) : (
              <div className="empty-state">
                <Icon name="browser" />
                <h2>Select a sandbox</h2>
                <p>
                  Choose a sandbox to view its details, open a session or
                  connect over CDP.
                </p>
              </div>
            )}
          </article>
        </section>
      </main>
    </div>
  );
}
