from fastapi import APIRouter, Depends

from app.deps import get_current_subject
from app.schemas.common import ApiEnvelope, ok
from app.schemas.sandbox import BrowserEngineAvailability
from app.services.engines import browser_engines

router = APIRouter(prefix="/runtime", tags=["runtime"], dependencies=[Depends(get_current_subject)])


@router.get("/engines", response_model=ApiEnvelope[list[BrowserEngineAvailability]])
async def list_browser_engines() -> ApiEnvelope[list[BrowserEngineAvailability]]:
    return ok(browser_engines())
