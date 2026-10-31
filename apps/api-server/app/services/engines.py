from app.config import get_settings
from app.models.sandbox import BrowserEngine, SandboxKind
from app.schemas.sandbox import BrowserEngineAvailability
from app.services.docker_adapter import docker_adapter


def cloak_unavailable_reason(kind: SandboxKind = SandboxKind.XVFB_VNC, *, image: str | None = None) -> str | None:
    settings = get_settings()
    if not settings.cloak_enabled:
        return "CloakBrowser is not configured. Follow docs/guides/cloak.md; Chromium needs no Cloak key."
    key = settings.cloak_license_file
    if key is None or not key.is_absolute() or not key.is_file() or key.stat().st_size == 0:
        return "Mount your Cloak key file on the server. A free GitHub key is supported."
    if not (settings.cloak_binary_dir / "current.json").is_file():
        return "Install the official Cloak binary first using the cloak-install service."
    if not docker_adapter.cloak_image_supported(image or settings.cloak_runtime_image_for_kind(kind)):
        return f"Cloak {kind.value} runtime image is missing or lacks a supported launcher; rebuild the image first."
    return None


def browser_engines() -> list[BrowserEngineAvailability]:
    reasons = {kind: cloak_unavailable_reason(kind) for kind in SandboxKind}
    kinds = [kind for kind, reason in reasons.items() if reason is None]
    camoufox_reason = camoufox_unavailable_reason()
    return [
        BrowserEngineAvailability(browser_engine=BrowserEngine.CHROMIUM, available=True, kinds=list(SandboxKind)),
        BrowserEngineAvailability(
            browser_engine=BrowserEngine.CLOAKBROWSER, available=bool(kinds),
            reason=None if kinds else reasons[SandboxKind.XVFB_VNC], kinds=kinds,
        ),
        BrowserEngineAvailability(
            browser_engine=BrowserEngine.CAMOUFOX, available=camoufox_reason is None,
            reason=camoufox_reason, kinds=[] if camoufox_reason else [SandboxKind.XVFB_VNC], automation="commands",
        ),
    ]


def camoufox_unavailable_reason(*, image: str | None = None) -> str | None:
    settings = get_settings()
    if not settings.camoufox_enabled:
        return "Camoufox is disabled. See docs/guides/camoufox.md."
    path = settings.camoufox_binary_dir
    if path is None or not path.is_absolute() or not (path / "camoufox-bin").is_file() or not (path / "version.json").is_file():
        return "Configure an absolute Camoufox binary directory with camoufox-bin and version.json."
    if not docker_adapter.camoufox_image_supported(image or settings.camoufox_runtime_image):
        return "Build a Camoufox runtime image with the supported launcher first."
    return None
