from __future__ import annotations

import hashlib
import importlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "apps/runtime-common"))
    return SimpleNamespace(
        runtime=importlib.import_module("cloak_runtime"),
        installer=importlib.import_module("install_cloak"),
        control=importlib.import_module("cloak_control"),
    )


@pytest.fixture
def installed(tmp_path, modules):
    runtime = modules.runtime
    artifact = "linux-x64-155.0.8059.39.1-" + "a" * 12
    release = tmp_path / "releases" / artifact
    binary = release / "binary/chrome"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"fake executable; never run")
    binary.chmod(0o755)
    build = runtime.InstalledBuild(
        artifact_id=artifact, version="155.0.8059.39.1", platform="linux-x64", executable="binary/chrome",
        executable_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(), archive_sha256="a" * 64,
        wrapper_version=runtime.WRAPPER_VERSION, channel="stable", installed_at="2026-01-01T00:00:00+00:00",
    )
    runtime.write_json(release / "manifest.json", asdict(build))
    runtime.write_json(tmp_path / "current.json", {"artifact_id": artifact})
    return tmp_path, build, binary


def test_build_manifest_and_no_implicit_install(modules, installed):
    root, build, binary = installed
    assert modules.runtime.installed_build(root) == (build, binary)
    binary.unlink()
    with pytest.raises(modules.runtime.RuntimeFailure, match="missing"):
        modules.runtime.installed_build(root)
    assert not binary.exists()


@pytest.mark.parametrize("artifact", ["../escape", "", "latest", None, 12])
def test_invalid_artifact_rejected(modules, installed, artifact):
    root, _, _ = installed
    modules.runtime.write_json(root / "current.json", {"artifact_id": artifact})
    with pytest.raises(modules.runtime.RuntimeFailure):
        modules.runtime.installed_build(root)


def test_prepare_profile_is_stable_and_not_rebound_to_current(modules, installed):
    root, build, _ = installed
    profile, state = root / "profile", root / "state"
    first = modules.runtime.prepare_profile(root, profile, state, "zh-CN", "UTC")
    modules.runtime.write_json(root / "current.json", {"artifact_id": "missing"})
    again = modules.runtime.prepare_profile(root, profile, state, "en-US", "UTC")
    assert first == again
    assert first["artifact_id"] == build.artifact_id
    assert first["locale"] == "zh-CN"
    assert (profile / ".cloakbrowser-seed").read_text().strip() == str(first["seed"])
    assert (state / "verge-profile.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("damage", ["missing", "corrupt", "different"])
def test_existing_seed_never_silently_rotates(modules, installed, damage):
    root, _, _ = installed
    profile, state = root / "profile", root / "state"
    modules.runtime.prepare_profile(root, profile, state, "en-US", "UTC")
    seed = profile / ".cloakbrowser-seed"
    if damage == "missing":
        seed.unlink()
    else:
        seed.write_text("broken" if damage == "corrupt" else "0")
    with pytest.raises(modules.runtime.RuntimeFailure):
        modules.runtime.prepare_profile(root, profile, state, "en-US", "UTC")


def test_prepare_refuses_existing_chromium_profile(modules, installed):
    root, _, _ = installed
    profile = root / "profile"
    profile.mkdir()
    (profile / "Local State").write_text("{}")
    with pytest.raises(modules.runtime.RuntimeFailure, match="empty profile"):
        modules.runtime.prepare_profile(root, profile, root / "state", "zh-CN", "UTC")


def test_native_headed_args_keep_verge_cdp_and_geometry(modules, installed):
    root, _, binary = installed
    saved = modules.runtime.prepare_profile(root, root / "profile", root / "state", "zh-CN", "UTC")
    args = modules.runtime.launch_args(binary, root / "profile", saved, {"BROWSER_WINDOW_WIDTH": "1400", "DEFAULT_URL": "--not-a-flag"})
    assert "--window-size=1400,1024" in args
    assert "--remote-debugging-port=9222" in args
    assert "--remote-debugging-address=127.0.0.1" in args
    assert f"--fingerprint={saved['seed']}" in args
    assert not any(a.startswith("--fingerprint-platform=") for a in args)
    assert "--enable-automation" not in args
    assert args[-2:] == ["--", "--not-a-flag"]


@pytest.mark.parametrize("env", [{"GPU_ENABLED": "true"}, {"HTTP_PROXY": "http://user:secret@proxy:80"}, {"BROWSER_WINDOW_WIDTH": "NaN"}])
def test_unsupported_launch_inputs_are_explicit(modules, installed, env):
    root, _, binary = installed
    saved = modules.runtime.prepare_profile(root, root / "profile", root / "state", "en-US", "UTC")
    with pytest.raises(modules.runtime.RuntimeFailure) as exc:
        modules.runtime.launch_args(binary, root / "profile", saved, env)
    assert "secret" not in str(exc.value)


def test_launch_uses_default_secret_file_and_exec_without_key_env(modules, installed, monkeypatch):
    root, build, binary = installed
    profile, state = root / "profile", root / ".cloakbrowser"
    modules.runtime.prepare_profile(root, profile, state, "en-US", "UTC")
    (state / "license.key").write_text("test-secret-not-real")
    monkeypatch.setattr(modules.runtime, "require_platform", lambda: None)
    monkeypatch.setattr(Path, "home", lambda: root)
    monkeypatch.setenv("CLOAKBROWSER_LICENSE_KEY", "must-not-be-inherited")
    monkeypatch.setenv("CLOAKBROWSER_DOWNLOAD_URL", "https://not-used.invalid")
    calls = []
    monkeypatch.setattr(modules.runtime.os, "execve", lambda *args: calls.append(args))
    modules.runtime.launch(root, profile, state, root / "run")
    executable, args, env = calls[0]
    assert executable == str(binary)
    assert "test-secret-not-real" not in str(args)
    assert "CLOAKBROWSER_LICENSE_KEY" not in env
    assert "CLOAKBROWSER_DOWNLOAD_URL" not in env
    assert env["TZ"] == "UTC"
    info = json.loads((root / "run/cloak-launch.json").read_text())
    assert info["build"]["artifact_id"] == build.artifact_id


def test_changed_binary_cannot_launch(modules, installed, monkeypatch):
    root, _, binary = installed
    profile, state = root / "profile", root / "state"
    modules.runtime.prepare_profile(root, profile, state, "en-US", "UTC")
    binary.write_bytes(b"changed")
    monkeypatch.setattr(modules.runtime, "require_platform", lambda: None)
    with pytest.raises(modules.runtime.RuntimeFailure, match="changed"):
        modules.runtime.launch(root, profile, state, root / "run")


@pytest.fixture
def official_fakes(monkeypatch, tmp_path, modules):
    key_file = tmp_path / "key"
    key_file.write_text("test-secret-not-real")
    monkeypatch.setattr(modules.installer, "require_platform", lambda: None)
    monkeypatch.setattr(modules.installer, "package_version", lambda name: "0.6.4")
    fake = SimpleNamespace(plan="solo", fail=False, calls=[])
    package = ModuleType("cloakbrowser")
    package.__path__ = []
    config = ModuleType("cloakbrowser.config")
    config.get_archive_name = lambda: "cloakbrowser-linux-x64.tar.gz"
    license_module = ModuleType("cloakbrowser.license")
    license_module.validate_license = lambda key: SimpleNamespace(valid=True, plan=fake.plan)
    license_module.get_pro_latest_version = lambda channel: "155.0.8059.39.1"
    download = ModuleType("cloakbrowser.download")

    def ensure_binary(**kwargs):
        fake.calls.append(kwargs)
        if fake.fail:
            raise RuntimeError("upstream detail with test-secret-not-real")
        cache = Path(modules.installer.os.environ["CLOAKBROWSER_CACHE_DIR"])
        binary = cache / "chromium-155.0.8059.39.1-pro/chrome"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"fake executable")
        binary.chmod(0o755)
        (binary.parent / "LICENSE").write_text("original license retained")
        return str(binary)

    download.ensure_binary = ensure_binary
    download._verify_signature = lambda manifest, signature: None
    download._parse_manifest_version = lambda text: "155.0.8059.39.1"
    download._parse_checksums = lambda text: {"cloakbrowser-linux-x64.tar.gz": "b" * 64}
    httpx = ModuleType("httpx")
    httpx.get = lambda *args, **kwargs: SimpleNamespace(content=b"signed-test-evidence", raise_for_status=lambda: None)
    for name, module in [("cloakbrowser", package), ("cloakbrowser.config", config), ("cloakbrowser.license", license_module), ("cloakbrowser.download", download), ("httpx", httpx)]:
        monkeypatch.setitem(sys.modules, name, module)
    # Keep installer environment mutations local to each test.
    monkeypatch.setattr(modules.installer.os, "environ", dict(modules.installer.os.environ))
    return fake, key_file


def test_install_requires_explicit_acceptance_before_any_download(modules, official_fakes, tmp_path):
    fake, key = official_fakes
    with pytest.raises(modules.runtime.RuntimeFailure, match="accept-binary-license"):
        modules.installer.install(tmp_path / "cache", key, False)
    assert fake.calls == []


def test_install_uses_official_pinned_wrapper_and_preserves_license(modules, official_fakes, tmp_path):
    fake, key = official_fakes
    root = tmp_path / "cache"
    modules.installer.os.environ["CLOAKBROWSER_BINARY_PATH"] = "not-used"
    result = modules.installer.install(root, key, True)
    assert fake.calls[0]["browser_version"] == "155.0.8059.39.1"
    assert fake.calls[0]["release_channel"] == "stable"
    assert "CLOAKBROWSER_BINARY_PATH" not in modules.installer.os.environ
    assert "CLOAKBROWSER_LICENSE_KEY" not in modules.installer.os.environ
    release = root / "releases" / result.artifact_id
    assert (release / "binary/LICENSE").read_text() == "original license retained"
    assert (release / "SHA256SUMS.sig").exists()
    assert modules.runtime.installed_build(root)[0] == result
    assert list((root / "staging").iterdir()) == []
    assert "test-secret" not in (release / "manifest.json").read_text()


def test_reinstall_keeps_existing_immutable_release(modules, official_fakes, tmp_path):
    _, key = official_fakes
    root = tmp_path / "cache"
    first = modules.installer.install(root, key, True)
    again = modules.installer.install(root, key, True)
    assert first == again
    assert len(list((root / "releases").iterdir())) == 1


def test_install_failure_preserves_current_and_sanitizes_evidence(modules, official_fakes, tmp_path):
    fake, key = official_fakes
    root = tmp_path / "cache"
    modules.runtime.write_json(root / "current.json", {"artifact_id": "previous"})
    fake.fail = True
    with pytest.raises(RuntimeError):
        modules.installer.install(root, key, True)
    assert json.loads((root / "current.json").read_text())["artifact_id"] == "previous"
    failure = next((root / "staging").glob("*/failure.json"))
    assert "test-secret" not in failure.read_text()


@pytest.mark.parametrize("phase", ["cleanup_staging", "publish_current"])
def test_install_finalization_failure_preserves_current_and_evidence(modules, official_fakes, tmp_path, monkeypatch, capsys, phase):
    _, key = official_fakes
    root = tmp_path / "cache"
    modules.runtime.write_json(root / "current.json", {"artifact_id": "previous"})
    real_write = modules.installer.write_json

    def fail_cleanup(path):
        raise PermissionError("private upstream detail")

    def fail_current(path, payload):
        if path == root / "current.json":
            assert list((root / "staging").iterdir()) == []
            raise OSError("private upstream detail")
        real_write(path, payload)

    if phase == "cleanup_staging":
        monkeypatch.setattr(modules.installer.shutil, "rmtree", fail_cleanup)
    else:
        monkeypatch.setattr(modules.installer, "write_json", fail_current)
    real_install = modules.installer.install
    monkeypatch.setattr(modules.installer, "install", lambda *args: real_install(root, key, True))
    monkeypatch.setattr(sys, "argv", ["install_cloak.py", "--accept-binary-license"])
    assert modules.installer.main() == 1
    error = json.loads(capsys.readouterr().err)
    assert "current was not changed" in error["message"]
    assert "private upstream detail" not in error["message"]
    assert json.loads((root / "current.json").read_text()) == {"artifact_id": "previous"}
    failure = json.loads(next((root / "staging").glob("*/failure.json")).read_text())
    assert failure["phase"] == phase
    assert len(list((root / "releases").iterdir())) == 1
    assert "CLOAKBROWSER_LICENSE_KEY" not in modules.installer.os.environ


def test_free_key_does_not_sneak_into_pinned_mode(modules, official_fakes, tmp_path):
    fake, key = official_fakes
    fake.plan = "free"
    with pytest.raises(modules.runtime.RuntimeFailure, match="free keys"):
        modules.installer.install(tmp_path / "cache", key, True)
    assert fake.calls == []


def test_bad_signature_does_not_publish_or_replace_current(modules, official_fakes, tmp_path):
    _, key = official_fakes
    root = tmp_path / "cache"
    modules.runtime.write_json(root / "current.json", {"artifact_id": "previous"})

    def reject(*args):
        raise RuntimeError("signature rejected")

    sys.modules["cloakbrowser.download"]._verify_signature = reject
    with pytest.raises(RuntimeError, match="signature"):
        modules.installer.install(root, key, True)
    assert not (root / "releases").exists()
    assert json.loads((root / "current.json").read_text())["artifact_id"] == "previous"
    failure = json.loads(next((root / "staging").glob("*/failure.json")).read_text())
    assert failure["phase"] == "retain_signed_receipt"


def test_missing_key_cannot_download(modules, official_fakes, tmp_path):
    fake, key = official_fakes
    key.unlink()
    with pytest.raises(modules.runtime.RuntimeFailure, match="license file"):
        modules.installer.install(tmp_path / "cache", key, True)
    assert fake.calls == []


@pytest.mark.parametrize("machine,system", [("arm64", "Linux"), ("x86_64", "Darwin")])
def test_unverified_platforms_fail_early(modules, monkeypatch, machine, system):
    monkeypatch.setattr(modules.runtime.platform, "machine", lambda: machine)
    monkeypatch.setattr(modules.runtime.platform, "system", lambda: system)
    with pytest.raises(modules.runtime.RuntimeFailure, match="Linux amd64"):
        modules.runtime.require_platform()


@pytest.mark.parametrize("exit_code,code", [(76, "SESSION_LIMIT"), (77, "LICENSE_INVALID"), (78, "LICENSE_UNREACHABLE"), (79, "LICENSE_CONFIG"), (1, "BROWSER_EXITED")])
def test_exit_diagnostics(modules, tmp_path, monkeypatch, exit_code, code):
    monkeypatch.setattr(modules.control, "process_info", lambda: {"statename": "EXITED", "exitstatus": exit_code})
    assert modules.control.diagnostics(tmp_path)["error"]["code"] == code


@pytest.mark.parametrize("state", ["EXITED", "STOPPED"])
def test_clean_stopped_browser_is_not_a_diagnostic_error(modules, tmp_path, monkeypatch, state):
    monkeypatch.setattr(modules.control, "process_info", lambda: {"statename": state, "exitstatus": 0})
    result = modules.control.diagnostics(tmp_path)
    assert result["process_state"] == state
    assert result["error"] is None


@pytest.mark.parametrize("state", ["FATAL", "BACKOFF"])
def test_failed_start_is_an_error_even_without_an_exit_code(modules, tmp_path, monkeypatch, state):
    monkeypatch.setattr(modules.control, "process_info", lambda: {"statename": state, "exitstatus": 0})
    assert modules.control.diagnostics(tmp_path)["error"]["code"] == "BROWSER_EXITED"


def test_post_handshake_license_denial_is_not_healthy(modules, tmp_path, monkeypatch):
    monkeypatch.setattr(modules.control, "process_info", lambda: {"statename": "RUNNING", "exitstatus": 0})
    denial = tmp_path / "cloak-denial-launch1.json"
    denial.write_text("76")
    modules.runtime.write_json(tmp_path / "cloak-launch.json", {"launch_id": "launch1", "build": {}, "denial_file": str(denial)})
    assert modules.control.diagnostics(tmp_path)["error"]["code"] == "SESSION_LIMIT"


@pytest.mark.parametrize("state,exit_code,denial,error,graceful", [
    ("EXITED", 0, None, None, True),
    ("EXITED", 1, None, "BROWSER_EXITED", False),
    ("EXITED", 77, None, "LICENSE_INVALID", False),
    ("EXITED", 0, 76, "SESSION_LIMIT", False),
    ("STOPPED", -15, None, None, False),
    ("FATAL", 0, None, "BROWSER_EXITED", False),
])
def test_stop_uses_browser_close_then_checks_exit(modules, tmp_path, monkeypatch, state, exit_code, denial, error, graceful):
    import io
    from contextlib import nullcontext
    from websockets.sync import client

    states = iter([{"statename": "RUNNING", "exitstatus": 0}, {"statename": state, "exitstatus": exit_code}])
    monkeypatch.setattr(modules.control, "process_info", lambda: next(states))
    if denial is not None:
        denial_file = tmp_path / "cloak-denial-launch1.json"
        denial_file.write_text(str(denial))
        modules.runtime.write_json(tmp_path / "cloak-launch.json", {"launch_id": "launch1", "build": {}, "denial_file": str(denial_file)})
    opener = SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(b'{"webSocketDebuggerUrl":"ws://wrong-host/devtools/browser/test"}'))
    monkeypatch.setattr(modules.control.urllib.request, "build_opener", lambda *args: opener)
    sent = []
    ws = SimpleNamespace(send=sent.append, recv=lambda **kwargs: b'{"id":1,"result":{}}')
    connected = []

    def connect(url, **kwargs):
        connected.append(url)
        return nullcontext(ws)

    monkeypatch.setattr(client, "connect", connect)
    result = modules.control.stop_browser(tmp_path)
    assert json.loads(sent[0])["method"] == "Browser.close"
    assert connected == ["ws://127.0.0.1:9222/devtools/browser/test"]
    assert result["graceful"] is graceful
    assert (result["error"]["code"] if result["error"] else None) == error
    assert result["seat_release"] == "unconfirmed"
    assert json.loads((tmp_path / "cloak-stop.json").read_text()) == result


@pytest.mark.parametrize("state,exit_code,error", [
    ("EXITED", 0, None),
    ("EXITED", 77, "LICENSE_INVALID"),
    ("FATAL", 0, "BROWSER_EXITED"),
    ("STOPPED", -15, None),
])
def test_already_exited_stop_propagates_error(modules, tmp_path, monkeypatch, state, exit_code, error):
    monkeypatch.setattr(modules.control, "process_info", lambda: {"statename": state, "exitstatus": exit_code})
    result = modules.control.stop_browser(tmp_path)
    assert result["already_exited"] is True
    assert result["graceful"] is False
    assert result["seat_release"] == "unconfirmed"
    assert (result["error"]["code"] if result["error"] else None) == error


@pytest.mark.parametrize("command,error,exit_code", [("stop", "LICENSE_INVALID", 1), ("status", None, 0)])
def test_control_cli_propagates_result_error(modules, tmp_path, monkeypatch, capsys, command, error, exit_code):
    monkeypatch.setattr(sys, "argv", ["cloak_control.py", command])
    monkeypatch.setattr(modules.control, "process_info", lambda: {"statename": "EXITED", "exitstatus": 77 if error else 0})
    monkeypatch.setattr(modules.control, "Path", lambda _: tmp_path)
    assert modules.control.main() == exit_code
    result = json.loads(capsys.readouterr().out)
    assert (result["error"]["code"] if result["error"] else None) == error


@pytest.mark.parametrize("exit_code,error", [(-15, None), (-9, None), (77, "LICENSE_INVALID")])
def test_stop_falls_back_to_supervisor_and_reports_warning(modules, tmp_path, monkeypatch, exit_code, error):
    from contextlib import nullcontext

    states = iter([{"statename": "RUNNING", "exitstatus": 0}, {"statename": "STOPPED", "exitstatus": exit_code}])
    monkeypatch.setattr(modules.control, "process_info", lambda: next(states))

    def unavailable(*args, **kwargs):
        raise OSError("CDP is down")

    monkeypatch.setattr(modules.control.urllib.request, "build_opener", lambda *args: SimpleNamespace(open=unavailable))
    stopped = []
    server = SimpleNamespace(supervisor=SimpleNamespace(stopProcess=lambda *args: stopped.append(args)))
    monkeypatch.setattr(modules.control.xmlrpc.client, "ServerProxy", lambda *args, **kwargs: nullcontext(server))
    result = modules.control.stop_browser(tmp_path)
    assert stopped == [("chromium", True)]
    assert result["graceful"] is False
    assert result["warning"]
    assert (result["error"]["code"] if result["error"] else None) == error


def test_runtime_script_keeps_chromium_default_and_disables_cloak_retries():
    root = Path(__file__).resolve().parents[2]
    script = (root / "apps/runtime-xvfb/scripts/start_all.sh").read_text()
    config = (root / "apps/runtime-xvfb/supervisor/supervisord.conf").read_text()
    assert '${BROWSER_ENGINE:-chromium}' in script
    assert "BROWSER_AUTORESTART=false BROWSER_STARTRETRIES=0" in script
    assert "[unix_http_server]" in config
    assert "startretries=%(ENV_BROWSER_STARTRETRIES)s" in config
    assert "BROWSER_STARTRETRIES=3 BROWSER_STOPASGROUP=false" in script
    assert "BROWSER_STARTRETRIES=3 BROWSER_STOPASGROUP=false BROWSER_STARTSECS=1" in script
    assert "BROWSER_STARTRETRIES=0 BROWSER_STOPASGROUP=true BROWSER_STARTSECS=0" in script
    assert "startsecs=%(ENV_BROWSER_STARTSECS)s" in config


def test_api_contract_does_not_pretend_experimental_engine_is_integrated():
    from app.schemas.sandbox import CreateSandboxRequest

    assert "browser_engine" not in CreateSandboxRequest.model_fields
