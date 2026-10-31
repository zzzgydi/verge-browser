"""Managed, single-owner Camoufox session. Reuses camoufox-cli's ref/command engine."""

import base64
import json
import os
from pathlib import Path
import signal
import socket

from camoufox.addons import DefaultAddons
from camoufox.sync_api import Camoufox
from camoufox_cli.browser import BrowserManager, TabView
from camoufox_cli.commands import execute, _resolve_ref
from camoufox_cli.identity import load_or_create, to_launch_kwargs
from camoufox_cli.refs import RefRegistry

SOCKET = "/run/sandbox/camoufox.sock"


def main():
    profile = os.environ.get("BROWSER_USER_DATA_DIR", "/workspace/browser-profile")
    identity = load_or_create(profile, locale="en-US", proxy=None, geoip=False)
    options = to_launch_kwargs(identity)
    manager = BrowserManager()
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    Path(SOCKET).unlink(missing_ok=True)
    # No private Xvfb, auto-spawn, idle watchdog or implicit browser recovery.
    with Camoufox(
        **options,
        headless=False,
        persistent_context=True,
        user_data_dir=profile,
        i_know_what_im_doing=True,
        exclude_addons=[DefaultAddons.UBO],
        no_viewport=True,
        accept_downloads=True,
        downloads_path="/workspace/downloads",
        window=(int(os.environ.get("BROWSER_WINDOW_WIDTH", "1280")), int(os.environ.get("BROWSER_WINDOW_HEIGHT", "1024"))),
    ) as context:
        context.set_default_timeout(10000)
        context.set_default_navigation_timeout(20000)
        manager._context = context
        page = context.pages[0] if context.pages else context.new_page()
        manager.state("default").page = page
        attached = set()

        def attach(page):
            if page in attached:
                return
            attached.add(page)
            page.on("close", lambda: attached.discard(page))

            def invalidate(frame):
                if frame == page.main_frame:
                    for state in manager._tabs.values():
                        if state.page == page:
                            state.refs = RefRegistry()

            page.on("framenavigated", invalidate)
            page.on(
                "download", lambda download: download.save_as(str(Path("/workspace/downloads") / Path(download.suggested_filename).name))
            )

        for page in context.pages:
            attach(page)
        context.on("page", attach)
        page.goto(os.environ.get("DEFAULT_URL", "about:blank"), wait_until="domcontentloaded")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(SOCKET)
            os.chmod(SOCKET, 0o600)
            server.listen(16)
            server.settimeout(0.2)
            try:
                while running:
                    # Pump Playwright events while humans browse or downloads finish.
                    page = next((p for p in context.pages if not p.is_closed()), None)
                    if page is not None:
                        page.wait_for_timeout(20)
                    try:
                        conn, _ = server.accept()
                    except socket.timeout:
                        continue
                    with conn:
                        conn.settimeout(30)
                        try:
                            command = json.loads(conn.makefile("rb").readline(1024 * 1024))
                            action = command["action"]
                            params = command.get("params", {})
                            view = TabView(manager, command.get("tab", "default"))
                            if action == "status":
                                page = manager.state("default").page
                                if page is None or page.is_closed():
                                    page = next((p for p in context.pages if not p.is_closed()), None)
                                if page is None:
                                    raise RuntimeError("No open page; use the session or explicitly restart the browser")
                                data = {
                                    "ready": True,
                                    "url": page.url,
                                    "version": page.evaluate("navigator.userAgent"),
                                    "viewport": page.evaluate(
                                        "({width:innerWidth,height:innerHeight,x:mozInnerScreenX-screenX,y:mozInnerScreenY-screenY})"
                                    ),
                                }
                            elif action == "stop":
                                # Close synchronously before acknowledging that the profile is saved.
                                context.close()
                                running = False
                                data = {"stopped": True}
                            elif action == "open":
                                page = view.get_page(create=True)
                                page.goto(params["url"], wait_until="domcontentloaded")
                                view._manager.state(view.tab).refs = RefRegistry()
                                page.bring_to_front()
                                data = {"url": page.url, "title": page.title()}
                            elif action == "click":
                                _resolve_ref(view, params["ref"]).click()
                                view._manager.state(view.tab).refs = RefRegistry()
                                data = {"url": view.get_page().url}
                            elif action == "upload":
                                path = Path(params["path"]).resolve()
                                if not path.is_relative_to("/workspace/uploads") or not path.is_file():
                                    raise ValueError("Upload path must be a file inside /workspace/uploads")
                                view.get_page().locator(params["selector"]).set_input_files(str(path))
                                data = {"uploaded": str(path)}
                            elif action == "screenshot":
                                image = view.get_page().screenshot(full_page=params.get("full", False))
                                data = {"data_base64": base64.b64encode(image).decode()}
                            elif action in {"snapshot", "fill", "press", "text", "tabs", "switch", "url", "title"}:
                                response = execute(manager, {"id": "verge", **command})
                                # Upstream acknowledges fill/press without a data member.
                                if response.get("success"):
                                    response.setdefault("data", {})
                                if action in {"fill", "press"}:
                                    view._manager.state(view.tab).refs = RefRegistry()
                                conn.sendall((json.dumps(response) + "\n").encode())
                                continue
                            else:
                                raise ValueError(f"Unsupported managed command: {action}")
                            response = {"success": True, "data": data}
                        except Exception as exc:
                            response = {"success": False, "error": str(exc)}
                        conn.sendall((json.dumps(response) + "\n").encode())
            finally:
                Path(SOCKET).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
