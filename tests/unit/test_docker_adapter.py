from __future__ import annotations

import subprocess
from pathlib import Path

from app.models.sandbox import SandboxKind
from app.services.docker_adapter import ContainerCreateResult, DockerAdapter


def test_create_container_passes_matching_xvfb_and_browser_dimensions(monkeypatch) -> None:
    adapter = DockerAdapter()
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool, **kwargs) -> subprocess.CompletedProcess:
        calls.append(cmd)
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        if cmd[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="cid-123\n", stderr="")
        if cmd[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout='[{"NetworkSettings":{"Networks":{"bridge":{"IPAddress":"172.17.0.2"}}}}]',
                stderr="",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", fake_run)

    result = adapter.create_container(
        sandbox_id="sb_test",
        kind=SandboxKind.XPRA,
        workspace_dir=Path("/tmp/workspace"),
        width=1440,
        height=900,
        default_url="about:blank",
        image="verge-browser-runtime-xpra:latest",
    )

    assert result == ContainerCreateResult(container_id="cid-123", host="172.17.0.2", error=None)
    docker_run = calls[1]
    assert "--name" in docker_run
    assert "verge-sandbox-sb_test" in docker_run
    assert "verge.managed=true" in docker_run
    assert "verge.sandbox.id=sb_test" in docker_run
    image_index = docker_run.index("verge-browser-runtime-xpra:latest")
    assert docker_run.index("XPRA_DISPLAY=:100") < image_index
    assert docker_run.index("XPRA_PORT=14500") < image_index
    assert "DISPLAY=:100" in docker_run
    assert "XPRA_DISPLAY=:100" in docker_run
    assert "XPRA_PORT=14500" in docker_run
    assert "BROWSER_WINDOW_WIDTH=1440" in docker_run
    assert "BROWSER_WINDOW_HEIGHT=900" in docker_run


def test_create_container_uses_xvfb_defaults_for_vnc_kind(monkeypatch) -> None:
    adapter = DockerAdapter()
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool, **kwargs) -> subprocess.CompletedProcess:
        calls.append(cmd)
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        if cmd[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="cid-456\n", stderr="")
        if cmd[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout='[{"NetworkSettings":{"Networks":{"bridge":{"IPAddress":"172.17.0.3"}}}}]',
                stderr="",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", fake_run)

    result = adapter.create_container(
        sandbox_id="sb_vnc",
        kind=SandboxKind.XVFB_VNC,
        workspace_dir=Path("/tmp/workspace"),
        width=1280,
        height=720,
        default_url="about:blank",
        image=None,
    )

    assert result == ContainerCreateResult(container_id="cid-456", host="172.17.0.3", error=None)
    docker_run = calls[1]
    image_index = docker_run.index("verge-browser-runtime-xvfb:latest")
    assert docker_run.index("XVFB_WHD=1280x720x24") < image_index
    assert docker_run.index("WEBSOCKET_PROXY_PORT=6080") < image_index
    assert "DISPLAY=:99" in docker_run
    assert "XVFB_WHD=1280x720x24" in docker_run
    assert "WEBSOCKET_PROXY_PORT=6080" in docker_run


def test_create_container_returns_stderr_when_docker_run_fails(monkeypatch) -> None:
    adapter = DockerAdapter()

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool, **kwargs) -> subprocess.CompletedProcess:
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.CalledProcessError(returncode=125, cmd=cmd, stderr="docker: Error response from daemon: invalid mount config")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", fake_run)

    result = adapter.create_container(
        sandbox_id="sb_bad",
        kind=SandboxKind.XVFB_VNC,
        workspace_dir=Path("/tmp/workspace"),
        width=1280,
        height=720,
        default_url="about:blank",
        image=None,
    )

    assert result.container_id is None
    assert result.host == "127.0.0.1"
    assert result.error == "docker: Error response from daemon: invalid mount config"


def test_remove_managed_containers_removes_all_labeled_containers(monkeypatch) -> None:
    adapter = DockerAdapter()
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool, **kwargs) -> subprocess.CompletedProcess:
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-aq"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="cid-1\ncid-2\n", stderr="")
        if cmd[:3] == ["docker", "rm", "-f"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", fake_run)

    adapter.remove_managed_containers()

    assert calls[0] == [
        "docker",
        "ps",
        "-aq",
        "--filter",
        "label=verge.managed=true",
    ]
    assert calls[1] == ["docker", "rm", "-f", "cid-1"]
    assert calls[2] == ["docker", "rm", "-f", "cid-2"]


def test_list_managed_container_refs_reads_sandbox_labels(monkeypatch) -> None:
    adapter = DockerAdapter()
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool, **kwargs) -> subprocess.CompletedProcess:
        calls.append(cmd)
        if cmd[:3] == ["docker", "ps", "-aq"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="cid-1\ncid-2\n", stderr="")
        if cmd[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="cid-1\tsb_1\ncid-2\t\n", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", fake_run)

    refs = adapter.list_managed_container_refs()

    assert calls[0] == [
        "docker",
        "ps",
        "-aq",
        "--filter",
        "label=verge.managed=true",
    ]
    assert calls[1] == [
        "docker",
        "inspect",
        "--format",
        '{{.Id}}\t{{index .Config.Labels "verge.sandbox.id"}}',
        "cid-1",
        "cid-2",
    ]
    assert [(ref.container_id, ref.sandbox_id) for ref in refs] == [("cid-1", "sb_1"), ("cid-2", None)]


def _make_fake_run(calls: list[list[str]], container_id: str = "cid-proxy"):
    """Return a fake subprocess.run that records docker commands."""
    import subprocess

    def fake_run(cmd: list[str], check: bool, capture_output: bool, text: bool, **kwargs) -> subprocess.CompletedProcess:
        calls.append(cmd)
        if cmd[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="[]", stderr="")
        if cmd[:2] == ["docker", "run"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{container_id}\n", stderr="")
        if cmd[:2] == ["docker", "inspect"]:
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout='[{"NetworkSettings":{"Networks":{"bridge":{"IPAddress":"172.17.0.5"}}}}]',
                stderr="",
            )
        raise AssertionError(f"unexpected command: {cmd}")

    return fake_run


def test_create_container_injects_http_proxy_only(monkeypatch) -> None:
    adapter = DockerAdapter()
    calls: list[list[str]] = []
    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", _make_fake_run(calls))

    adapter.create_container(
        sandbox_id="sb_p1",
        kind=SandboxKind.XVFB_VNC,
        workspace_dir=Path("/tmp/ws"),
        width=1280,
        height=1024,
        default_url=None,
        image="verge-browser-runtime-xvfb:latest",
        http_proxy="http://proxy.corp:8080",
    )

    docker_run = calls[1]
    assert "HTTP_PROXY=http://proxy.corp:8080" in docker_run
    assert "http_proxy=http://proxy.corp:8080" in docker_run
    assert not any(v.startswith("HTTPS_PROXY=") for v in docker_run)
    assert not any(v.startswith("https_proxy=") for v in docker_run)
    # Default no_proxy injected when http_proxy is active
    assert "NO_PROXY=localhost,127.0.0.1" in docker_run
    assert "no_proxy=localhost,127.0.0.1" in docker_run


def test_create_container_injects_https_proxy_only(monkeypatch) -> None:
    adapter = DockerAdapter()
    calls: list[list[str]] = []
    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", _make_fake_run(calls))

    adapter.create_container(
        sandbox_id="sb_p2",
        kind=SandboxKind.XVFB_VNC,
        workspace_dir=Path("/tmp/ws"),
        width=1280,
        height=1024,
        default_url=None,
        image="verge-browser-runtime-xvfb:latest",
        https_proxy="http://proxy.corp:8080",
    )

    docker_run = calls[1]
    assert not any(v.startswith("HTTP_PROXY=") for v in docker_run)
    assert not any(v.startswith("http_proxy=") for v in docker_run)
    assert "HTTPS_PROXY=http://proxy.corp:8080" in docker_run
    assert "https_proxy=http://proxy.corp:8080" in docker_run
    assert "NO_PROXY=localhost,127.0.0.1" in docker_run
    assert "no_proxy=localhost,127.0.0.1" in docker_run


def test_create_container_injects_all_three_proxy_fields(monkeypatch) -> None:
    adapter = DockerAdapter()
    calls: list[list[str]] = []
    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", _make_fake_run(calls))

    adapter.create_container(
        sandbox_id="sb_p3",
        kind=SandboxKind.XVFB_VNC,
        workspace_dir=Path("/tmp/ws"),
        width=1280,
        height=1024,
        default_url=None,
        image="verge-browser-runtime-xvfb:latest",
        http_proxy="http://proxy.corp:8080",
        https_proxy="http://proxy.corp:8443",
        no_proxy="localhost,127.0.0.1,.internal",
    )

    docker_run = calls[1]
    assert "HTTP_PROXY=http://proxy.corp:8080" in docker_run
    assert "http_proxy=http://proxy.corp:8080" in docker_run
    assert "HTTPS_PROXY=http://proxy.corp:8443" in docker_run
    assert "https_proxy=http://proxy.corp:8443" in docker_run
    assert "NO_PROXY=localhost,127.0.0.1,.internal" in docker_run
    assert "no_proxy=localhost,127.0.0.1,.internal" in docker_run


def test_create_container_no_proxy_env_when_proxy_omitted(monkeypatch) -> None:
    adapter = DockerAdapter()
    calls: list[list[str]] = []
    monkeypatch.setattr("app.services.docker_adapter.subprocess.run", _make_fake_run(calls))

    adapter.create_container(
        sandbox_id="sb_p4",
        kind=SandboxKind.XVFB_VNC,
        workspace_dir=Path("/tmp/ws"),
        width=1280,
        height=1024,
        default_url=None,
        image="verge-browser-runtime-xvfb:latest",
    )

    docker_run = calls[1]
    for var in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy"):
        assert not any(v.startswith(f"{var}=") for v in docker_run), f"unexpected {var} in command"
