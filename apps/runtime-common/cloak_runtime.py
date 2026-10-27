"""Experimental Xvfb launcher. Installation is an explicit, separate operation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import secrets
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

WRAPPER_VERSION = "0.6.4"
POLICY_VERSION = 1
ARTIFACT_PATTERN = re.compile(r"linux-x64-[0-9]+(?:\.[0-9]+){3,4}-[0-9a-f]{12}")


class RuntimeFailure(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        json.dump(payload, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeFailure("INVALID_STATE", f"Cannot read valid JSON from {path.name}; preserve the file and inspect it.") from exc
    if not isinstance(value, dict):
        raise RuntimeFailure("INVALID_STATE", f"Expected an object in {path.name}.")
    return value


def require_platform() -> None:
    if platform.system() != "Linux" or platform.machine() not in {"x86_64", "amd64"}:
        raise RuntimeFailure("UNSUPPORTED_PLATFORM", "The Cloak experiment currently supports Linux amd64 containers only.")


@dataclass(frozen=True)
class InstalledBuild:
    artifact_id: str
    version: str
    platform: str
    executable: str
    executable_sha256: str
    archive_sha256: str
    wrapper_version: str
    channel: str
    installed_at: str


def installed_build(root: Path, artifact_id: str | None = None) -> tuple[InstalledBuild, Path]:
    if artifact_id is None:
        artifact_id = read_json(root / "current.json").get("artifact_id")
    if not isinstance(artifact_id, str) or not ARTIFACT_PATTERN.fullmatch(artifact_id):
        raise RuntimeFailure("INVALID_ARTIFACT", "A valid installed Cloak artifact is required; run the explicit installer first.")
    release = root / "releases" / artifact_id
    try:
        build = InstalledBuild(**read_json(release / "manifest.json"))
    except TypeError as exc:
        raise RuntimeFailure("INVALID_ARTIFACT", "The Cloak installation manifest has an unsupported layout.") from exc
    if (
        build.artifact_id != artifact_id
        or build.platform != "linux-x64"
        or build.wrapper_version != WRAPPER_VERSION
        or build.channel != "stable"
        or build.executable != "binary/chrome"
        or not isinstance(build.version, str)
        or not re.fullmatch(r"[0-9]+(?:\.[0-9]+){3,4}", build.version)
        or not isinstance(build.archive_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", build.archive_sha256)
        or not isinstance(build.executable_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", build.executable_sha256)
        or artifact_id != f"linux-x64-{build.version}-{build.archive_sha256[:12]}"
    ):
        raise RuntimeFailure("INVALID_ARTIFACT", "The Cloak installation does not match this launcher/platform.")
    executable = release / build.executable
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeFailure("BINARY_MISSING", "The installed Cloak executable is missing or not executable; do not fall back to Chromium.")
    if executable.resolve().parent != (release / "binary").resolve():
        raise RuntimeFailure("INVALID_ARTIFACT", "The Cloak executable must belong to its installed release.")
    return build, executable


def profile_state(profile: Path, state: Path) -> dict:
    payload = read_json(state / "verge-profile.json")
    seed = payload.get("seed")
    if (
        payload.get("policy_version") != POLICY_VERSION
        or type(seed) is not int
        or not 10000 <= seed <= 99999
        or not isinstance(payload.get("artifact_id"), str)
        or not ARTIFACT_PATTERN.fullmatch(payload["artifact_id"])
        or not isinstance(payload.get("locale"), str)
        or not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", payload["locale"])
        or not isinstance(payload.get("timezone"), str)
    ):
        raise RuntimeFailure("INVALID_PROFILE", "The saved Cloak profile configuration is invalid; do not regenerate its identity.")
    try:
        ZoneInfo(payload["timezone"])
        stored_seed = (profile / ".cloakbrowser-seed").read_text(encoding="utf-8").strip()
    except (OSError, ValueError, KeyError) as exc:
        raise RuntimeFailure("INVALID_PROFILE", "The saved Cloak seed/timezone is unavailable; preserve the profile for repair.") from exc
    if stored_seed != str(seed):
        raise RuntimeFailure("SEED_MISMATCH", "The Cloak seed differs from its saved identity; refusing to rotate it.")
    return payload


def prepare_profile(root: Path, profile: Path, state: Path, locale: str, timezone: str) -> dict:
    if (state / "verge-profile.json").exists():
        saved = profile_state(profile, state)
        installed_build(root, saved["artifact_id"])
        return saved
    if profile.exists() and any(profile.iterdir()):
        raise RuntimeFailure("PROFILE_NOT_EMPTY", "Use a new empty profile; importing or switching an existing browser profile is not supported.")
    if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", locale):
        raise RuntimeFailure("INVALID_LOCALE", "Provide a locale such as zh-CN or en-US.")
    try:
        ZoneInfo(timezone)
    except (ValueError, KeyError) as exc:
        raise RuntimeFailure("INVALID_TIMEZONE", "Provide an installed IANA timezone such as UTC or Asia/Shanghai.") from exc
    build, _ = installed_build(root)
    seed = secrets.randbelow(90000) + 10000
    profile.mkdir(parents=True, exist_ok=True)
    seed_path = profile / ".cloakbrowser-seed"
    with seed_path.open("x", encoding="utf-8") as stream:
        os.chmod(seed_path, 0o600)
        stream.write(f"{seed}\n")
        stream.flush()
        os.fsync(stream.fileno())
    payload = {"policy_version": POLICY_VERSION, "artifact_id": build.artifact_id, "seed": seed, "locale": locale, "timezone": timezone}
    write_json(state / "verge-profile.json", payload)
    return payload


def launch_args(executable: Path, profile: Path, saved: dict, env: dict[str, str]) -> list[str]:
    try:
        width, height = int(env.get("BROWSER_WINDOW_WIDTH", "1280")), int(env.get("BROWSER_WINDOW_HEIGHT", "1024"))
    except ValueError as exc:
        raise RuntimeFailure("INVALID_DISPLAY", "Browser dimensions must be integers.") from exc
    if not 320 <= width <= 7680 or not 240 <= height <= 4320:
        raise RuntimeFailure("INVALID_DISPLAY", "Browser dimensions are out of range.")
    # Keep the native Linux persona and real X11 geometry; do not inherit the
    # wrapper's Windows override or add a CDP-emulated viewport.
    args = [
        str(executable), "--no-sandbox", "--no-first-run", "--no-default-browser-check",
        "--gtk-version=3", "--ozone-platform=x11", "--enable-input-method-proxy",
        "--disable-dev-shm-usage", "--disable-popup-blocking", "--ignore-gpu-blocklist",
        f"--fingerprint={saved['seed']}", f"--lang={saved['locale']}", f"--fingerprint-locale={saved['locale']}",
        f"--fingerprint-timezone={saved['timezone']}", f"--display={env.get('DISPLAY', ':99')}",
        f"--user-data-dir={profile}", "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9222",
        "--window-position=0,0", f"--window-size={width},{height}", "--start-maximized",
        "--disk-cache-dir=/tmp/chrome-cache", "--force-color-profile=srgb", "--license-route=auto",
    ]
    # Hardware GPU and authenticated proxies need their own real-runtime tests.
    if env.get("GPU_ENABLED", "false") != "false":
        raise RuntimeFailure("UNSUPPORTED_GPU", "Hardware GPU is not enabled for the initial Cloak experiment.")
    args.append("--disable-gpu")
    http_proxy, https_proxy = env.get("HTTP_PROXY", ""), env.get("HTTPS_PROXY", "")
    if any("@" in value for value in (http_proxy, https_proxy)):
        raise RuntimeFailure("UNSUPPORTED_PROXY", "Authenticated proxies are not enabled for the initial Cloak experiment.")
    if http_proxy or https_proxy:
        proxy = f"http={http_proxy};https={https_proxy}" if http_proxy and https_proxy else http_proxy or https_proxy
        args.append(f"--proxy-server={proxy}")
        args.append(f"--proxy-bypass-list={env.get('NO_PROXY', 'localhost,127.0.0.1')}")
    args.extend(["--", env.get("DEFAULT_URL", "about:blank")])
    return args


def launch(root: Path, profile: Path, state: Path, run_dir: Path) -> None:
    require_platform()
    # An attempted restart must not retain the previous launch's denial signal.
    (run_dir / "cloak-launch.json").unlink(missing_ok=True)
    saved = profile_state(profile, state)
    build, executable = installed_build(root, saved["artifact_id"])
    with executable.open("rb") as stream:
        actual_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual_hash != build.executable_sha256:
        raise RuntimeFailure("BINARY_CHANGED", "The installed executable changed; prepare a verified installation before retrying.")
    # The binary reads this default path itself; never put the key in argv/env.
    if state.resolve() != (Path.home() / ".cloakbrowser").resolve():
        raise RuntimeFailure("INVALID_STATE_DIR", "Mount per-sandbox state at ~/.cloakbrowser so the binary can find its key and writable state.")
    key_file = state / "license.key"
    if not key_file.is_file() or not key_file.read_text(encoding="utf-8").strip():
        raise RuntimeFailure("LICENSE_MISSING", "Mount the deployment's Cloak license file read-only at ~/.cloakbrowser/license.key.")
    env = {key: value for key, value in os.environ.items() if not key.startswith("CLOAKBROWSER_")}
    env["TZ"] = saved["timezone"]
    run_dir.mkdir(parents=True, exist_ok=True)
    launch_id = uuid.uuid4().hex
    env["CLOAKBROWSER_LICENSE_STATUS_FILE"] = str(run_dir / f"cloak-denial-{launch_id}.json")
    args = launch_args(executable, profile, saved, env)
    Path("/tmp/chrome-cache").mkdir(exist_ok=True)
    write_json(run_dir / "cloak-launch.json", {"launch_id": launch_id, "build": asdict(build), "denial_file": env["CLOAKBROWSER_LICENSE_STATUS_FILE"]})
    (run_dir / "cloak-error.json").unlink(missing_ok=True)
    os.execve(str(executable), args, env)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "info", "launch"])
    args = parser.parse_args()
    root = Path(os.environ.get("VERGE_CLOAK_ROOT", "/opt/verge/cloak"))
    profile = Path(os.environ.get("BROWSER_USER_DATA_DIR", "/workspace/browser-profile"))
    state = Path.home() / ".cloakbrowser"
    run_dir = Path("/run/sandbox")
    try:
        require_platform()
        if args.command == "prepare":
            result = prepare_profile(root, profile, state, os.environ.get("VERGE_CLOAK_LOCALE", "zh-CN"), os.environ.get("VERGE_CLOAK_TIMEZONE", "UTC"))
        elif args.command == "info":
            result = asdict(installed_build(root)[0])
        else:
            launch(root, profile, state, run_dir)
            return 0
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # Do not echo arbitrary upstream exceptions or proxy/key values.
        failure = {"code": exc.code, "message": str(exc)} if isinstance(exc, RuntimeFailure) else {
            "code": "RUNTIME_ERROR", "message": f"Runtime preparation failed ({type(exc).__name__}); inspect the mounted configuration."
        }
        if args.command == "launch":
            write_json(run_dir / "cloak-error.json", failure)
        print(json.dumps(failure), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
