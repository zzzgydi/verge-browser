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


@pytest.mark.parametrize("display", [":99", ":100"])
def test_native_headed_args_keep_verge_cdp_and_geometry(modules, installed, display):
    root, _, binary = installed
    saved = modules.runtime.prepare_profile(root, root / "profile", root / "state", "zh-CN", "UTC")
    args = modules.runtime.launch_args(binary, root / "profile", saved, {"DISPLAY": display, "BROWSER_WINDOW_WIDTH": "1400", "DEFAULT_URL": "--not-a-flag"})
    assert f"--display={display}" in args
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
    fake = SimpleNamespace(
        plan="solo", valid=True, fail=False, calls=[], version_calls=[], receipt_urls=[],
        latest_version="155.0.8059.39.1", downloaded_version="155.0.8059.39.1", manifest_version=None,
        directory=None,
    )
    package = ModuleType("cloakbrowser")
    package.__path__ = []
    config = ModuleType("cloakbrowser.config")
    config.get_archive_name = lambda: "cloakbrowser-linux-x64.tar.gz"
    license_module = ModuleType("cloakbrowser.license")
    license_module.validate_license = lambda key: SimpleNamespace(valid=fake.valid, plan=fake.plan)

    def get_pro_latest_version(channel):
        fake.version_calls.append(channel)
        return fake.latest_version

    license_module.get_pro_latest_version = get_pro_latest_version
    download = ModuleType("cloakbrowser.download")

    def ensure_binary(**kwargs):
        fake.calls.append(kwargs)
        if fake.fail:
            raise RuntimeError("upstream detail with test-secret-not-real")
        cache = Path(modules.installer.os.environ["CLOAKBROWSER_CACHE_DIR"])
        binary = cache / (fake.directory or f"chromium-{fake.downloaded_version}-pro") / "chrome"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"fake executable")
        binary.chmod(0o755)
        (binary.parent / "LICENSE").write_text("original license retained")
        return str(binary)

    download.ensure_binary = ensure_binary
    download._verify_signature = lambda manifest, signature: None
    download._parse_manifest_version = lambda text: fake.manifest_version or fake.downloaded_version
    download._parse_checksums = lambda text: {"cloakbrowser-linux-x64.tar.gz": "b" * 64}
    httpx = ModuleType("httpx")

    def get_receipt(url, **kwargs):
        fake.receipt_urls.append(url)
        return SimpleNamespace(content=b"signed-test-evidence", raise_for_status=lambda: None)

    httpx.get = get_receipt
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


@pytest.mark.parametrize("plan", ["free", "solo"])
def test_install_failure_preserves_current_and_sanitizes_evidence(modules, official_fakes, tmp_path, plan):
    fake, key = official_fakes
    fake.plan = plan
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


def test_free_key_installs_official_latest_without_a_pin(modules, official_fakes, tmp_path):
    fake, key = official_fakes
    fake.plan = "free"
    fake.downloaded_version = "156.0.8078.47.1"
    modules.installer.os.environ["CLOAKBROWSER_VERSION"] = "154.0.0.0.1"
    root = tmp_path / "cache"
    result = modules.installer.install(root, key, True)
    assert fake.calls == [{"license_key": "test-secret-not-real", "browser_version": None, "release_channel": "stable"}]
    assert fake.version_calls == []
    assert "CLOAKBROWSER_VERSION" not in modules.installer.os.environ
    assert "CLOAKBROWSER_LICENSE_KEY" not in modules.installer.os.environ
    assert result.version == fake.downloaded_version
    source = f"https://cloakbrowser.dev/releases/pro/chromium-v{fake.downloaded_version}"
    assert fake.receipt_urls == [f"{source}/SHA256SUMS", f"{source}/SHA256SUMS.sig"]
    assert modules.runtime.installed_build(root)[0] == result


@pytest.mark.parametrize("plan", ["free", "solo"])
def test_invalid_key_does_not_download(modules, official_fakes, tmp_path, plan):
    fake, key = official_fakes
    fake.plan, fake.valid = plan, False
    with pytest.raises(modules.runtime.RuntimeFailure, match="could not validate"):
        modules.installer.install(tmp_path / "cache", key, True)
    assert fake.calls == []


@pytest.mark.parametrize("plan", ["free", "solo"])
def test_manifest_version_mismatch_preserves_current(modules, official_fakes, tmp_path, plan):
    fake, key = official_fakes
    fake.plan = plan
    fake.manifest_version = "154.0.0.0.1"
    root = tmp_path / "cache"
    modules.runtime.write_json(root / "current.json", {"artifact_id": "previous"})
    with pytest.raises(modules.runtime.RuntimeFailure, match="signed release manifest"):
        modules.installer.install(root, key, True)
    assert not (root / "releases").exists()
    assert json.loads((root / "current.json").read_text())["artifact_id"] == "previous"


def test_paid_key_still_requires_the_resolved_version(modules, official_fakes, tmp_path):
    fake, key = official_fakes
    fake.downloaded_version = "154.0.0.0.1"
    with pytest.raises(modules.runtime.RuntimeFailure, match="requested Stable version"):
        modules.installer.install(tmp_path / "cache", key, True)
    assert fake.receipt_urls == []


@pytest.mark.parametrize("directory", ["chromium-146.0.7680.177.5", "chromium-latest-pro", "other"])
def test_free_key_rejects_keyless_or_unknown_layout(modules, official_fakes, tmp_path, directory):
    fake, key = official_fakes
    fake.plan, fake.directory = "free", directory
    with pytest.raises(modules.runtime.RuntimeFailure, match="unexpected Linux binary layout"):
        modules.installer.install(tmp_path / "cache", key, True)
    assert fake.receipt_urls == []


@pytest.mark.parametrize("plan", ["free", "solo"])
def test_bad_signature_does_not_publish_or_replace_current(modules, official_fakes, tmp_path, plan):
    fake, key = official_fakes
    fake.plan = plan
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


@pytest.mark.parametrize("runtime", ["runtime-xvfb", "runtime-xpra"])
def test_runtime_script_keeps_chromium_default_and_disables_cloak_retries(runtime):
    root = Path(__file__).resolve().parents[2]
    script = (root / "apps" / runtime / "scripts/start_all.sh").read_text()
    config = (root / "apps" / runtime / "supervisor/supervisord.conf").read_text()
    browser = (root / "apps" / runtime / "scripts/start_browser.sh").read_text()
    dockerfile = (root / "docker" / f"{runtime}.Dockerfile").read_text()
    assert '${BROWSER_ENGINE:-chromium}' in script
    assert "BROWSER_AUTORESTART=false BROWSER_STARTRETRIES=0" in script
    assert "[unix_http_server]" in config
    assert "startretries=%(ENV_BROWSER_STARTRETRIES)s" in config
    assert "BROWSER_STARTRETRIES=3 BROWSER_STOPASGROUP=false" in script
    assert "BROWSER_STARTRETRIES=3 BROWSER_STOPASGROUP=false BROWSER_STARTSECS=1" in script
    assert "BROWSER_STARTRETRIES=0 BROWSER_STOPASGROUP=true BROWSER_STARTSECS=0" in script
    assert "startsecs=%(ENV_BROWSER_STARTSECS)s" in config
    assert "stopasgroup=%(ENV_BROWSER_STOPASGROUP)s" in config
    assert "killasgroup=%(ENV_BROWSER_STOPASGROUP)s" in config
    assert "/run/sandbox/supervisor.sock" in config
    assert "cloak_runtime.py prepare" in script
    assert "cloak_runtime.py launch" in browser
    assert browser.index("cloak_runtime.py launch") < browser.index("exec chromium")
    assert "COPY apps/runtime-common/*.py /opt/sandbox/cloak/" in dockerfile
    assert 'io.verge.browser.launcher-version="1"' in dockerfile
    assert 'io.verge.browser.experimental-engines="cloakbrowser-linux-amd64"' in dockerfile
    assert "--require-hashes" in dockerfile
    assert "cloakbrowser install" not in dockerfile


def test_api_contract_exposes_engine_with_chromium_default():
    from app.schemas.sandbox import CreateSandboxRequest

    assert CreateSandboxRequest().browser_engine == "chromium"
    assert CreateSandboxRequest(browser_engine="cloakbrowser").browser_engine == "cloakbrowser"


@pytest.mark.parametrize("engine,prepare_exit", [("chromium", 0), ("cloakbrowser", 0), ("cloakbrowser", 1), ("unknown", 0)])
def test_xpra_entrypoint_prepares_cloak_before_supervisor(tmp_path, engine, prepare_exit):
    import os
    import subprocess

    root = Path(__file__).resolve().parents[2]
    launcher = tmp_path / "prepare"
    launcher.write_text(f'#!/bin/sh\necho prepare >> "$TRACE"\nexit {prepare_exit}\n')
    supervisor = tmp_path / "supervisor"
    supervisor.write_text('#!/bin/sh\nprintf "supervisor:%s:%s:%s:%s\\n" "$BROWSER_AUTORESTART" "$BROWSER_STARTRETRIES" "$BROWSER_STOPASGROUP" "$BROWSER_STARTSECS" >> "$TRACE"\n')
    launcher.chmod(0o755)
    supervisor.chmod(0o755)
    script = (root / "apps/runtime-xpra/scripts/start_all.sh").read_text()
    script = script.replace("/opt/sandbox/cloak-venv/bin/python", str(launcher)).replace("/usr/bin/supervisord", str(supervisor))
    trace = tmp_path / "trace"
    result = subprocess.run(["bash", "-c", script], env={**os.environ, "BROWSER_ENGINE": engine, "TRACE": str(trace)}, capture_output=True, text=True)
    events = trace.read_text().splitlines() if trace.exists() else []
    if engine == "chromium":
        assert result.returncode == 0 and events == ["supervisor:true:3:false:1"]
    elif engine == "cloakbrowser" and prepare_exit == 0:
        assert result.returncode == 0 and events == ["prepare", "supervisor:false:0:true:0"]
    else:
        assert result.returncode != 0
        assert events == (["prepare"] if engine == "cloakbrowser" else [])


def test_control_start_clears_stale_denial_before_supervisor_start(modules, tmp_path, monkeypatch, capsys):
    from contextlib import nullcontext

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "cloak-launch.json").write_text('{"old": true}')
    (run_dir / "cloak-error.json").write_text('{"old": true}')
    real_path = Path
    monkeypatch.setattr(modules.control, "Path", lambda value: run_dir if value == "/run/sandbox" else real_path(value))
    monkeypatch.setattr(modules.control, "process_info", lambda: {"statename": "EXITED", "exitstatus": 76})
    called = []
    def start(name, wait):
        assert not (run_dir / "cloak-launch.json").exists()
        assert not (run_dir / "cloak-error.json").exists()
        called.append((name, wait))
    server = SimpleNamespace(supervisor=SimpleNamespace(startProcess=start))
    monkeypatch.setattr(modules.control.xmlrpc.client, "ServerProxy", lambda *args, **kwargs: nullcontext(server))
    monkeypatch.setattr(sys, "argv", ["cloak_control.py", "start"])
    assert modules.control.main() == 0
    assert json.loads(capsys.readouterr().out)["started"] is True
    assert called == [("chromium", True)]
