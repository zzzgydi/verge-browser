from __future__ import annotations

import glob
import json
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.models.sandbox import BrowserEngine, SandboxKind


@dataclass(frozen=True)
class ManagedContainer:
    container_id: str
    sandbox_id: str | None


@dataclass(frozen=True)
class ContainerCreateResult:
    container_id: str | None
    host: str
    error: str | None = None


class DockerAdapter:
    managed_label_key = "verge.managed"
    managed_label_value = "true"
    sandbox_label_key = "verge.sandbox.id"

    def is_available(self) -> bool:
        try:
            proc = subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError:
            return False
        except subprocess.TimeoutExpired:
            return False
        return proc.returncode == 0

    def image_exists(self, image_name: str) -> bool:
        try:
            proc = subprocess.run(
                ["docker", "image", "inspect", image_name],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return proc.returncode == 0

    def create_container(
        self,
        *,
        sandbox_id: str,
        kind: SandboxKind,
        workspace_dir: Path,
        width: int,
        height: int,
        default_url: str | None,
        image: str | None,
        browser_engine: BrowserEngine = BrowserEngine.CHROMIUM,
        enable_gpu: bool = False,
        http_proxy: str | None = None,
        https_proxy: str | None = None,
        no_proxy: str | None = None,
    ) -> ContainerCreateResult:
        settings = get_settings()
        image_name = image or (settings.cloak_runtime_image if browser_engine == BrowserEngine.CLOAKBROWSER else settings.runtime_image_for_kind(kind))
        if not self.image_exists(image_name):
            return ContainerCreateResult(
                container_id=None,
                host="127.0.0.1",
                error=f"runtime image '{image_name}' is not built locally",
            )
        container_name = f"verge-sandbox-{sandbox_id}"
        display = settings.display_for_kind(kind)
        session_port = settings.session_port_for_kind(kind)

        # Detect available GPU hardware on the host for device pass-through (Linux-only).
        # This is independent of GPU_ENABLED: even without hardware, GPU_ENABLED=true
        # lets the container fall back to SwiftShader software WebGL rendering.
        gpu_device: str | None = None
        if enable_gpu and platform.system() == "Linux":
            if Path("/dev/nvidia0").exists():
                gpu_device = "nvidia"
            elif glob.glob("/dev/dri/renderD*"):
                gpu_device = "dri"

        shm_size = "2g" if enable_gpu else "1g"

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            f"--shm-size={shm_size}",
            "--network",
            settings.sandbox_runtime_network,
            "--label",
            f"{self.managed_label_key}={self.managed_label_value}",
            "--label",
            f"{self.sandbox_label_key}={sandbox_id}",
            "-e",
            f"SANDBOX_ID={sandbox_id}",
            "-e",
            f"DISPLAY={display}",
            "-e",
            f"BROWSER_WINDOW_WIDTH={width}",
            "-e",
            f"BROWSER_WINDOW_HEIGHT={height}",
            "-e",
            f"DEFAULT_URL={default_url or settings.sandbox_default_url}",
            "-e",
            f"GPU_ENABLED={'true' if enable_gpu else 'false'}",
            "-e",
            f"BROWSER_ENGINE={browser_engine.value}",
            "-v",
            f"{workspace_dir}:/workspace",
        ]

        if browser_engine == BrowserEngine.CLOAKBROWSER:
            state = workspace_dir.parent / "cloak-state"
            state.mkdir(mode=0o700, parents=True, exist_ok=True)
            cmd.extend([
                "--platform", "linux/amd64",
                "--label", "verge.browser.engine=cloakbrowser",
                "--mount", f"type=volume,src={settings.cloak_binary_volume},dst=/opt/verge/cloak,readonly",
                "--mount", f"type=bind,src={state},dst=/root/.cloakbrowser",
                "--mount", f"type=bind,src={settings.cloak_license_file},dst=/root/.cloakbrowser/license.key,readonly",
                "-e", f"VERGE_CLOAK_LOCALE={settings.cloak_locale}",
                "-e", f"VERGE_CLOAK_TIMEZONE={settings.cloak_timezone}",
            ])

        if http_proxy:
            cmd.extend(["-e", f"HTTP_PROXY={http_proxy}", "-e", f"http_proxy={http_proxy}"])
        if https_proxy:
            cmd.extend(["-e", f"HTTPS_PROXY={https_proxy}", "-e", f"https_proxy={https_proxy}"])
        # Always set NO_PROXY when any proxy is active; fall back to safe default.
        effective_no_proxy = no_proxy if no_proxy is not None else ("localhost,127.0.0.1" if (http_proxy or https_proxy) else None)
        if effective_no_proxy is not None:
            cmd.extend(["-e", f"NO_PROXY={effective_no_proxy}", "-e", f"no_proxy={effective_no_proxy}"])

        if gpu_device == "nvidia":
            # NVIDIA GPU: use NVIDIA Container Toolkit (requires nvidia-container-toolkit on host)
            cmd.extend(["--gpus", "all"])
        elif gpu_device == "dri":
            # Intel/AMD: pass through DRI render nodes for Mesa EGL
            cmd.extend(["--device", "/dev/dri:/dev/dri"])

        if kind == SandboxKind.XPRA:
            cmd.extend(
                ["-e", f"XPRA_DISPLAY={display}", "-e", f"XPRA_PORT={session_port}"]
            )
        else:
            cmd.extend(
                [
                    "-e",
                    f"XVFB_WHD={width}x{height}x24",
                    "-e",
                    f"WEBSOCKET_PROXY_PORT={session_port}",
                ]
            )
        cmd.append(image_name)
        try:
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            return ContainerCreateResult(
                container_id=None,
                host="127.0.0.1",
                error="docker CLI not found on PATH",
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            if not detail:
                detail = "docker run exited with a non-zero status"
            return ContainerCreateResult(
                container_id=None, host="127.0.0.1", error=detail
            )
        container_id = proc.stdout.strip()
        host = self.inspect_container_ip(container_id)
        return ContainerCreateResult(
            container_id=container_id, host=host or "127.0.0.1"
        )

    def inspect_container_ip(self, container_id: str) -> str | None:
        try:
            proc = subprocess.run(
                ["docker", "inspect", container_id],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None
        data = json.loads(proc.stdout)
        networks = data[0].get("NetworkSettings", {}).get("Networks", {})
        for network in networks.values():
            ip = network.get("IPAddress")
            if ip:
                return ip
        return None

    def remove_container(self, container_id: str) -> bool:
        try:
            result = subprocess.run(
                ["docker", "rm", "-f", container_id],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return result.returncode == 0 or "No such container:" in result.stderr

    def cloak_control(self, container_id: str, command: str) -> dict:
        try:
            result = subprocess.run(
                ["docker", "exec", container_id, "/opt/sandbox/cloak-venv/bin/python",
                 "/opt/sandbox/cloak/cloak_control.py", command],
                check=False, capture_output=True, text=True, timeout=45 if command == "stop" else 8,
            )
            payload = json.loads(result.stdout)
            if isinstance(payload, dict) and "error" in payload:
                if result.returncode == 0 or payload["error"]:
                    return payload
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass
        return {"error": {"code": "CONTROL_UNAVAILABLE", "message": "Cloak browser control unavailable; preserve the container and inspect its logs."}}

    def start_cloak_browser(self, container_id: str) -> bool:
        result = self.cloak_control(container_id, "start")
        return bool(result.get("started")) and not result.get("error")

    def list_managed_containers(self) -> list[str]:
        try:
            proc = subprocess.run(
                [
                    "docker",
                    "ps",
                    "-aq",
                    "--filter",
                    f"label={self.managed_label_key}={self.managed_label_value}",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return []
        return [line for line in proc.stdout.splitlines() if line]

    def list_managed_container_refs(self) -> list[ManagedContainer]:
        container_ids = self.list_managed_containers()
        if not container_ids:
            return []
        try:
            proc = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    f'{{{{.Id}}}}\t{{{{index .Config.Labels "{self.sandbox_label_key}"}}}}',
                    *container_ids,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except (FileNotFoundError, subprocess.CalledProcessError):
            return []
        refs: list[ManagedContainer] = []
        for line in proc.stdout.splitlines():
            if not line:
                continue
            container_id, _, sandbox_id = line.partition("\t")
            refs.append(
                ManagedContainer(
                    container_id=container_id, sandbox_id=sandbox_id or None
                )
            )
        return refs

    def remove_managed_containers(self) -> None:
        for container_id in self.list_managed_containers():
            self.remove_container(container_id)

    def container_exists(self, container_id: str) -> bool:
        try:
            proc = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", container_id],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return False
        return proc.returncode == 0 and proc.stdout.strip() == "true"

    def restart_browser(self, container_id: str) -> bool:
        try:
            proc = subprocess.run(
                [
                    "docker",
                    "exec",
                    container_id,
                    "supervisorctl",
                    "restart",
                    "chromium",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return False
        return proc.returncode == 0

    def exec(
        self,
        container_id: str,
        argv: list[str],
        *,
        text: bool = True,
        check: bool = False,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "exec", container_id, *argv],
            check=check,
            capture_output=True,
            text=text,
        )

    def exec_shell(
        self, container_id: str, script: str, *, text: bool = True, check: bool = False
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "exec", container_id, "/bin/bash", "-lc", script],
            check=check,
            capture_output=True,
            text=text,
        )


docker_adapter = DockerAdapter()
