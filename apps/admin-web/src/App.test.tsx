import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { SWRConfig } from "swr";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { App } from "./App";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const sandbox = {
  id: "sb_test",
  alias: "research-browser",
  kind: "xvfb_vnc",
  browser_engine: "chromium",
  status: "RUNNING",
  width: 1440,
  height: 900,
  enable_gpu: false,
  created_at: "2026-10-29T08:20:00Z",
  updated_at: "2026-10-29T08:21:00Z",
  metadata: {},
};

const engines = [
  {
    browser_engine: "chromium",
    available: true,
    reason: null,
    kinds: ["xvfb_vnc", "xpra"],
  },
  {
    browser_engine: "cloakbrowser",
    available: true,
    reason: null,
    kinds: ["xvfb_vnc"],
  },
];

function response(data: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    json: async () => ({
      code: status,
      message: status < 400 ? "OK" : "Service unavailable",
      data,
    }),
  };
}

function renderApp() {
  return render(
    <SWRConfig
      value={{
        provider: () => new Map(),
        dedupingInterval: 0,
        shouldRetryOnError: false,
      }}
    >
      <App />
    </SWRConfig>,
  );
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("verge-browser.admin.token", "test-token");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      response(
        url.endsWith("/runtime/engines")
          ? engines
          : url.endsWith("/sandbox")
            ? [sandbox]
            : sandbox,
      ),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("sandbox dashboard", () => {
  it("keeps the title and console actions in one header", async () => {
    renderApp();
    const header = screen.getByRole("banner");
    expect(
      within(header).getByRole("heading", {
        level: 1,
        name: "Verge Browser",
      }),
    ).toBeTruthy();
    expect(
      within(header).getByRole("button", { name: /Refresh|Syncing/ }),
    ).toBeTruthy();
    expect(within(header).getByRole("button", { name: "Logout" })).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(within(header).queryByText("Sandbox Control")).toBeNull();
    await screen.findByRole("button", { name: /research-browser/ });
  });

  it("pairs each sandbox status with a distinct icon without duplicating its accessible name", async () => {
    const statuses = ["RUNNING", "STOPPED", "STARTING", "DEGRADED", "FAILED"];
    vi.mocked(fetch).mockImplementation(
      async (url) =>
        response(
          String(url).endsWith("/runtime/engines")
            ? engines
            : statuses.map((status) => ({
                ...sandbox,
                id: status,
                alias: `fixture-${status}`,
                status,
              })),
        ) as Response,
    );
    renderApp();
    await screen.findByRole("button", { name: /fixture-RUNNING/ });
    const paths = statuses.map((status) => {
      const row = screen.getByRole("button", {
        name: new RegExp(`fixture-${status}`),
      });
      const icon = row.querySelector(".status svg");
      expect(icon?.getAttribute("aria-hidden")).toBe("true");
      expect(within(row).getByText(status.toLowerCase())).toBeTruthy();
      return icon?.querySelector("path")?.getAttribute("d");
    });
    expect(new Set(paths).size).toBe(statuses.length);
  });

  it("requires a token and saves a normalized API URL", async () => {
    localStorage.clear();
    renderApp();
    expect(
      (screen.getByLabelText("Admin Token") as HTMLInputElement).required,
    ).toBe(true);
    fireEvent.change(screen.getByLabelText("API URL"), {
      target: { value: "http://localhost:8000/" },
    });
    fireEvent.change(screen.getByLabelText("Admin Token"), {
      target: { value: "test-token" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open Console" }));
    expect(
      await screen.findByRole("heading", { name: "Verge Browser" }),
    ).toBeTruthy();
    expect(localStorage.getItem("verge-browser.admin.api-url")).toBe(
      "http://localhost:8000",
    );
  });

  it("filters the list and can recover from no matches", async () => {
    renderApp();
    await screen.findByRole("button", { name: /research-browser/ });
    fireEvent.change(screen.getByLabelText("Search sandboxes"), {
      target: { value: "missing" },
    });
    expect(screen.getByText("No matching sandboxes")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(
      screen.getByRole("button", { name: /research-browser/ }),
    ).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Search sandboxes"), {
      target: { value: "RUNNING" },
    });
    expect(
      screen.getByRole("button", { name: /research-browser/ }),
    ).toBeTruthy();
  });

  it("keeps loading and API failure distinct from an empty list", async () => {
    let finish: (value: ReturnType<typeof response>) => void = () => {};
    vi.mocked(fetch).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve as typeof finish;
        }),
    );
    renderApp();
    expect(screen.getByText("Loading sandboxes...")).toBeTruthy();
    expect(screen.queryByText("No sandboxes yet")).toBeNull();
    cleanup();
    finish(response(engines));
    vi.mocked(fetch).mockImplementation(
      async () => response(null, 503) as Response,
    );
    renderApp();
    expect(await screen.findByText("Could not load sandboxes")).toBeTruthy();
    expect(screen.queryByText("No sandboxes yet")).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });

  it("refreshes the selected details after pausing and does not show Creating", async () => {
    let status = "RUNNING";
    vi.mocked(fetch).mockImplementation(async (url, init) => {
      const path = String(url);
      if (path.endsWith("/pause") && init?.method === "POST")
        status = "STOPPED";
      return response(
        path.endsWith("/runtime/engines")
          ? engines
          : path.endsWith("/sandbox")
            ? [{ ...sandbox, status }]
            : { ...sandbox, status },
      ) as Response;
    });
    renderApp();
    fireEvent.click(
      await screen.findByRole("button", { name: /research-browser/ }),
    );
    fireEvent.click(await screen.findByRole("button", { name: "Pause" }));
    expect(screen.queryByText("Creating...")).toBeNull();
    await waitFor(() =>
      expect(
        (screen.getByRole("button", { name: "Resume" }) as HTMLButtonElement)
          .disabled,
      ).toBe(false),
    );
    expect(
      (
        screen.getByRole("button", {
          name: "Open Session",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      within(
        screen.getByRole("article", { name: "Sandbox details" }),
      ).getByText("stopped"),
    ).toBeTruthy();
  });

  it("preserves Cloak runtime restrictions and submits the chosen configuration", async () => {
    vi.mocked(fetch).mockImplementation(
      async (url, init) =>
        response(
          String(url).endsWith("/runtime/engines")
            ? engines
            : init?.method === "POST"
              ? { ...sandbox, ...JSON.parse(String(init.body)) }
              : String(url).endsWith("/sandbox")
                ? [sandbox]
                : sandbox,
        ) as Response,
    );
    renderApp();
    await screen.findByRole("button", { name: /research-browser/ });
    fireEvent.change(screen.getByLabelText("Desktop runtime"), {
      target: { value: "xpra" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Enable GPU/ }));
    fireEvent.change(screen.getByLabelText("Browser engine"), {
      target: { value: "cloakbrowser" },
    });
    const gpu = screen.getByRole("checkbox", {
      name: /Enable GPU/,
    }) as HTMLInputElement;
    expect(gpu.checked).toBe(false);
    expect(gpu.disabled).toBe(true);
    expect(
      (screen.getByLabelText("Desktop runtime") as HTMLSelectElement).value,
    ).toBe("xvfb_vnc");
    fireEvent.change(screen.getByLabelText(/Alias/), {
      target: { value: "cloak-test" },
    });
    fireEvent.change(screen.getByLabelText("Resolution"), {
      target: { value: "1920x1080" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Sandbox" }));
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(/\/sandbox$/),
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            alias: "cloak-test",
            kind: "xvfb_vnc",
            browser_engine: "cloakbrowser",
            width: 1920,
            height: 1080,
            enable_gpu: false,
          }),
        }),
      ),
    );
  });

  it("copies a CDP URL with the selected ticket preset", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    vi.mocked(fetch).mockImplementation(
      async (url) =>
        response(
          String(url).endsWith("/cdp/apply")
            ? { cdp_url: "ws://localhost/test-ticket" }
            : String(url).endsWith("/runtime/engines")
              ? engines
              : String(url).endsWith("/sandbox")
                ? [sandbox]
                : sandbox,
        ) as Response,
    );
    renderApp();
    fireEvent.click(
      await screen.findByRole("button", { name: /research-browser/ }),
    );
    fireEvent.change(await screen.findByLabelText("CDP link expiry"), {
      target: { value: "permanent" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Connect CDP" }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith("ws://localhost/test-ticket"),
    );
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/cdp\/apply$/),
      expect.objectContaining({ body: JSON.stringify({ mode: "permanent" }) }),
    );
  });

  it("reports popup and network failures instead of silently swallowing them", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    renderApp();
    fireEvent.click(
      await screen.findByRole("button", { name: /research-browser/ }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Open Session" }),
    );
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "Popup blocked. Allow popups for this site and retry.",
      ),
    );
    vi.mocked(fetch).mockRejectedValue(new TypeError("Failed to fetch"));
    fireEvent.click(screen.getByRole("button", { name: "Create Sandbox" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Failed to fetch"),
    );
    expect(
      (
        screen.getByRole("button", {
          name: "Create Sandbox",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false);
  });

  it("shows an actionable first-run empty state", async () => {
    vi.mocked(fetch).mockImplementation(
      async (url) =>
        response(String(url).endsWith("/sandbox") ? [] : engines) as Response,
    );
    renderApp();
    expect(await screen.findByText("No sandboxes yet")).toBeTruthy();
    expect(screen.getByText("Create a sandbox to get started.")).toBeTruthy();
  });

  it("shows detail failures without claiming nothing was selected", async () => {
    vi.mocked(fetch).mockImplementation(async (url) =>
      String(url).endsWith("/sb_test")
        ? (response(null, 503) as Response)
        : (response(
            String(url).endsWith("/runtime/engines") ? engines : [sandbox],
          ) as Response),
    );
    renderApp();
    fireEvent.click(
      await screen.findByRole("button", { name: /research-browser/ }),
    );
    expect(await screen.findByText("Could not load this sandbox")).toBeTruthy();
    expect(screen.queryByText("Select a sandbox")).toBeNull();
  });

  it("opens a ticketed session with the chosen expiry", async () => {
    const replace = vi.fn();
    const popup = {
      opener: window,
      document: { title: "", body: { innerHTML: "" } },
      location: { replace },
      close: vi.fn(),
    };
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    vi.mocked(fetch).mockImplementation(
      async (url) =>
        response(
          String(url).endsWith("/session/apply")
            ? { session_url: "http://localhost/session-fixture" }
            : String(url).endsWith("/runtime/engines")
              ? engines
              : String(url).endsWith("/sandbox")
                ? [sandbox]
                : sandbox,
        ) as Response,
    );
    renderApp();
    fireEvent.click(
      await screen.findByRole("button", { name: /research-browser/ }),
    );
    fireEvent.change(await screen.findByLabelText("Session link expiry"), {
      target: { value: "one_time_60" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Open Session" }));
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith("http://localhost/session-fixture"),
    );
    expect(popup.opener).toBeNull();
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/session\/apply$/),
      expect.objectContaining({
        body: JSON.stringify({ mode: "one_time", ttl_sec: 60 }),
      }),
    );
  });
});
