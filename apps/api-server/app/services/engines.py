from app.config import get_settings
from app.models.sandbox import BrowserEngine, SandboxKind
from app.schemas.sandbox import BrowserEngineAvailability
from app.services.docker_adapter import docker_adapter


def cloak_unavailable_reason() -> str | None:
    settings = get_settings()
    if not settings.cloak_enabled:
        return "CloakBrowser is not configured. Follow docs/guides/cloak.md; Chromium needs no Cloak key."
    key = settings.cloak_license_file
    if key is None or not key.is_absolute() or not key.is_file() or key.stat().st_size == 0:
        return "Mount your Cloak key file on the server. A free GitHub key is supported."
    if not (settings.cloak_binary_dir / "current.json").is_file():
        return "Install the official Cloak binary first using the cloak-install service."
    if not docker_adapter.image_exists(settings.cloak_runtime_image):
        return "Build the configured Cloak runtime image first."
    return None


def browser_engines() -> list[BrowserEngineAvailability]:
    reason = cloak_unavailable_reason()
    return [
        BrowserEngineAvailability(browser_engine=BrowserEngine.CHROMIUM, available=True, kinds=list(SandboxKind)),
        BrowserEngineAvailability(browser_engine=BrowserEngine.CLOAKBROWSER, available=reason is None, reason=reason, kinds=[SandboxKind.XVFB_VNC]),
    ]
