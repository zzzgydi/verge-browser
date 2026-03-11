from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.routes.browser import router as browser_router
from app.routes.files import router as files_router
from app.routes.health import router as health_router
from app.routes.sandboxes import router as sandbox_router
from app.routes.vnc import router as vnc_router
from app.services.registry import registry


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    registry.load_from_disk(
        settings.sandbox_base_dir,
        workspace_subdir=settings.workspace_subdir,
        downloads_subdir=settings.downloads_subdir,
        uploads_subdir=settings.uploads_subdir,
        browser_profile_subdir=settings.browser_profile_subdir,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    app.include_router(health_router)
    app.include_router(sandbox_router)
    app.include_router(browser_router)
    app.include_router(vnc_router)
    app.include_router(files_router)
    return app


app = create_app()
