from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.models.sandbox import SandboxKind


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
            proc = subprocess.run(["docker", "info"], check=False, capture_output=True, text=True, timeout=5)
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
    ) -> ContainerCreateResult:
        settings = get_settings()
        image_name = image or settings.runtime_image_for_kind(kind)
        if not self.image_exists(image_name):
            return ContainerCreateResult(container_id=None, host="127.0.0.1", error=f"runtime image '{image_name}' is not built locally")
        container_name = f"verge-sandbox-{sandbox_id}"
        display = settings.display_for_kind(kind)
        session_port = settings.session_port_for_kind(kind)
        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            "--shm-size=1g",
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
            "-v",
            f"{workspace_dir}:/workspace",
        ]
        if kind == SandboxKind.XPRA:
            cmd.extend(["-e", f"XPRA_DISPLAY={display}", "-e", f"XPRA_PORT={session_port}"])
        else:
            cmd.extend(["-e", f"XVFB_WHD={width}x{height}x24", "-e", f"WEBSOCKET_PROXY_PORT={session_port}"])
        cmd.append(image_name)
        try:
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            return ContainerCreateResult(container_id=None, host="127.0.0.1", error="docker CLI not found on PATH")
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            if not detail:
                detail = "docker run exited with a non-zero status"
            return ContainerCreateResult(container_id=None, host="127.0.0.1", error=detail)
        container_id = proc.stdout.strip()
        host = self.inspect_container_ip(container_id)
        return ContainerCreateResult(container_id=container_id, host=host or "127.0.0.1")

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

    def remove_container(self, container_id: str) -> None:
        try:
            subprocess.run(["docker", "rm", "-f", container_id], check=False, capture_output=True, text=True)
        except FileNotFoundError:
            return

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
            refs.append(ManagedContainer(container_id=container_id, sandbox_id=sandbox_id or None))
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
                ["docker", "exec", container_id, "supervisorctl", "restart", "chromium"],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            return False
        return proc.returncode == 0

    def exec(self, container_id: str, argv: list[str], *, text: bool = True, check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "exec", container_id, *argv],
            check=check,
            capture_output=True,
            text=text,
        )

    def exec_shell(self, container_id: str, script: str, *, text: bool = True, check: bool = False) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["docker", "exec", container_id, "/bin/bash", "-lc", script],
            check=check,
            capture_output=True,
            text=text,
        )


docker_adapter = DockerAdapter()
