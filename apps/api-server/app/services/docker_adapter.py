from __future__ import annotations

import json
import subprocess
from pathlib import Path

from app.config import get_settings


class DockerAdapter:
    def is_available(self) -> bool:
        try:
            proc = subprocess.run(["docker", "info"], check=False, capture_output=True, text=True)
        except FileNotFoundError:
            return False
        return proc.returncode == 0

    def create_container(self, *, sandbox_id: str, workspace_dir: Path, width: int, height: int, default_url: str | None, image: str | None) -> tuple[str | None, str]:
        settings = get_settings()
        image_name = image or settings.sandbox_runtime_image
        cmd = [
            "docker",
            "run",
            "-d",
            "--shm-size=1g",
            "--network",
            settings.sandbox_runtime_network,
            "-e",
            f"SANDBOX_ID={sandbox_id}",
            "-e",
            f"BROWSER_WINDOW_WIDTH={width}",
            "-e",
            f"BROWSER_WINDOW_HEIGHT={height}",
            "-e",
            f"DEFAULT_URL={default_url or settings.sandbox_default_url}",
            "-v",
            f"{workspace_dir}:/workspace",
            image_name,
        ]
        try:
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            return None, "127.0.0.1"
        container_id = proc.stdout.strip()
        host = self.inspect_container_ip(container_id)
        return container_id, host or "127.0.0.1"

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
