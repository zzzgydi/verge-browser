"""Install an official, signed Cloak build into a deployment-private volume."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path

from cloak_runtime import InstalledBuild, RuntimeFailure, WRAPPER_VERSION, installed_build, require_platform, write_json

LICENSE_URL = "https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md"


def install(root: Path, key_file: Path, accepted: bool) -> InstalledBuild:
    if not accepted:
        raise RuntimeFailure("LICENSE_NOT_ACCEPTED", f"Read {LICENSE_URL}, then explicitly pass --accept-binary-license for your internal deployment.")
    require_platform()
    if package_version("cloakbrowser") != WRAPPER_VERSION:
        raise RuntimeFailure("WRAPPER_MISMATCH", f"This installer requires cloakbrowser {WRAPPER_VERSION}.")
    try:
        key = key_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise RuntimeFailure("LICENSE_MISSING", "Mount your own license file read-only before running the installer.") from exc
    if not key:
        raise RuntimeFailure("LICENSE_MISSING", "The mounted license file is empty.")

    staging_root = root / "staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="install-", dir=staging_root))
    cache = staging / "cache"
    # This is a dedicated installer process. Never accept wrapper download,
    # checksum, binary-path or channel overrides from its inherited environment.
    for name in tuple(os.environ):
        if name.startswith("CLOAKBROWSER_"):
            del os.environ[name]
    os.environ.update({"CLOAKBROWSER_CACHE_DIR": str(cache), "CLOAKBROWSER_AUTO_UPDATE": "false", "CLOAKBROWSER_LICENSE_KEY": key})
    logging.getLogger("cloakbrowser").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)
    phase = "validate_license"
    try:
        import httpx
        from cloakbrowser.config import get_archive_name
        from cloakbrowser.download import _parse_checksums, _parse_manifest_version, _verify_signature, ensure_binary
        from cloakbrowser.license import get_pro_latest_version, validate_license

        entitlement = validate_license(key)
        if entitlement is None or not entitlement.valid:
            raise RuntimeFailure("LICENSE_INVALID", "The official service could not validate this key; check the subscription and network.")
        if entitlement.plan == "free":
            raise RuntimeFailure("PIN_NOT_AVAILABLE", "This version-pinned experiment requires a plan supporting pinning; free keys are not supported.")
        phase = "resolve_stable"
        release_version = get_pro_latest_version("stable")
        if not release_version:
            raise RuntimeFailure("VERSION_UNAVAILABLE", "The official Stable version could not be resolved.")
        phase = "download_and_verify"
        binary = Path(ensure_binary(license_key=key, browser_version=release_version, release_channel="stable"))
        if binary.parent.parent.resolve() != cache.resolve() or binary.name != "chrome":
            raise RuntimeFailure("INSTALL_LAYOUT", "The official installer returned an unexpected Linux binary layout.")

        # The pinned wrapper has already verified the archive before extraction.
        # Retain the signed release evidence as well, without retaining credentials.
        phase = "retain_signed_receipt"
        source = f"https://cloakbrowser.dev/releases/pro/chromium-v{release_version}"
        manifest_response = httpx.get(f"{source}/SHA256SUMS", follow_redirects=True, timeout=15)
        manifest_response.raise_for_status()
        signature_response = httpx.get(f"{source}/SHA256SUMS.sig", follow_redirects=True, timeout=15)
        signature_response.raise_for_status()
        _verify_signature(manifest_response.content, signature_response.content)
        signed_text = manifest_response.content.decode("utf-8")
        if _parse_manifest_version(signed_text) != release_version:
            raise RuntimeFailure("VERSION_MISMATCH", "The signed release manifest does not match the installed version.")
        archive_hash = _parse_checksums(signed_text).get(get_archive_name())
        if not archive_hash:
            raise RuntimeFailure("CHECKSUM_MISSING", "The signed release manifest has no entry for this platform.")
        with binary.open("rb") as stream:
            executable_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        artifact_id = f"linux-x64-{release_version}-{archive_hash[:12]}"
        build = InstalledBuild(
            artifact_id=artifact_id, version=release_version, platform="linux-x64", executable="binary/chrome",
            executable_sha256=executable_hash, archive_sha256=archive_hash, wrapper_version=WRAPPER_VERSION,
            channel="stable", installed_at=datetime.now(timezone.utc).isoformat(),
        )
        phase = "publish_installation"
        prepared = staging / "release"
        prepared.mkdir()
        binary.parent.rename(prepared / "binary")
        (prepared / "SHA256SUMS").write_bytes(manifest_response.content)
        (prepared / "SHA256SUMS.sig").write_bytes(signature_response.content)
        write_json(prepared / "manifest.json", asdict(build))
        releases = root / "releases"
        releases.mkdir(exist_ok=True)
        destination = releases / artifact_id
        if destination.exists():
            existing, existing_binary = installed_build(root, artifact_id)
            with existing_binary.open("rb") as stream:
                existing_hash = hashlib.file_digest(stream, "sha256").hexdigest()
            if existing_hash != executable_hash or existing.executable_sha256 != executable_hash:
                raise RuntimeFailure("EXISTING_BUILD_CHANGED", "An existing immutable installation differs; preserve it and investigate.")
            build = existing
        else:
            prepared.rename(destination)
        installed_build(root, artifact_id)
        phase = "cleanup_staging"
        shutil.rmtree(staging)
        # Commit last so every reported installation failure leaves current intact.
        phase = "publish_current"
        write_json(root / "current.json", {"artifact_id": artifact_id})
    except Exception as exc:
        write_json(staging / "failure.json", {
            "code": exc.code if isinstance(exc, RuntimeFailure) else "INSTALL_FAILED",
            "exception_type": type(exc).__name__,
            "phase": phase,
        })
        raise
    finally:
        os.environ.pop("CLOAKBROWSER_LICENSE_KEY", None)
    return build


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accept-binary-license", action="store_true")
    args = parser.parse_args()
    try:
        build = install(Path("/opt/verge/cloak"), Path("/run/secrets/cloak-license"), args.accept_binary_license)
    except Exception as exc:
        error = {"code": exc.code, "message": str(exc)} if isinstance(exc, RuntimeFailure) else {
            "code": "INSTALL_FAILED", "message": f"Official installation failed ({type(exc).__name__}); current was not changed. Inspect staging/failure.json."
        }
        print(json.dumps(error), file=sys.stderr)
        return 1
    print(json.dumps(asdict(build), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
