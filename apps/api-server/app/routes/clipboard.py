from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.deps import require_sandbox
from app.routes import session as session_route
from app.schemas.browser import ClipboardReadResponse, ClipboardWriteRequest, ClipboardWriteResponse
from app.services.clipboard import ClipboardError, clipboard_service

router = APIRouter(prefix="/sandbox/{sandbox_id}", tags=["clipboard"])


def _error_response(exc: ClipboardError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "code": exc.code, "message": exc.message})


@router.get("/clipboard")
async def get_clipboard(
    sandbox_id: str,
    sandbox=Depends(require_sandbox),
    sandbox_session: str | None = Cookie(default=None),
) -> JSONResponse:
    try:
        session_route._validate_session(sandbox_session, session_route._canonical_sandbox_id(sandbox, sandbox_id))
        text = await clipboard_service.read_text(sandbox)
        payload = ClipboardReadResponse(status="ok", text=text)
        return JSONResponse(status_code=200, content=payload.model_dump())
    except ClipboardError as exc:
        return _error_response(exc)


@router.post("/clipboard")
async def set_clipboard(
    request: Request,
    sandbox_id: str,
    sandbox=Depends(require_sandbox),
    sandbox_session: str | None = Cookie(default=None),
) -> JSONResponse:
    try:
        session_route._validate_session(sandbox_session, session_route._canonical_sandbox_id(sandbox, sandbox_id))
        content_type = request.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            return JSONResponse(
                status_code=415,
                content={"status": "error", "code": "unsupported_media_type", "message": "content-type must be application/json"},
            )
        payload = ClipboardWriteRequest.model_validate(await request.json())
        await clipboard_service.write_text(sandbox, payload.text)
        response = ClipboardWriteResponse(status="ok")
        return JSONResponse(status_code=200, content=response.model_dump())
    except ClipboardError as exc:
        return _error_response(exc)
    except ValidationError as exc:
        message = "; ".join(error.get("msg", "invalid value") for error in exc.errors()) or "request body is invalid"
        return JSONResponse(status_code=400, content={"status": "error", "code": "invalid_request", "message": message})
    except ValueError:
        return JSONResponse(status_code=400, content={"status": "error", "code": "invalid_json", "message": "request body must be valid JSON"})
