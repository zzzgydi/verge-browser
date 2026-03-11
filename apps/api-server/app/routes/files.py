from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.deps import get_current_subject, require_sandbox
from app.schemas.files import FileEntry, WriteFileRequest
from app.services.files import file_service

router = APIRouter(prefix="/sandboxes/{sandbox_id}/files", tags=["files"], dependencies=[Depends(get_current_subject)])


@router.get("/list", response_model=list[FileEntry])
async def list_files(path: str = Query("/workspace"), sandbox=Depends(require_sandbox)) -> list[FileEntry]:
    return file_service.list(sandbox, path)


@router.get("/read")
async def read_file(path: str = Query(...), sandbox=Depends(require_sandbox)) -> dict[str, str]:
    return {"path": path, "content": file_service.read_text(sandbox, path)}


@router.post("/write")
async def write_file(payload: WriteFileRequest, sandbox=Depends(require_sandbox)) -> dict[str, str]:
    target = file_service.write_text(sandbox, payload.path, payload.content, payload.overwrite)
    return {"path": str(target)}


@router.post("/upload")
async def upload_file(upload: UploadFile = File(...), sandbox=Depends(require_sandbox)) -> dict[str, str]:
    target = await file_service.upload(sandbox, upload)
    return {"path": str(target)}


@router.get("/download")
async def download_file(path: str = Query(...), sandbox=Depends(require_sandbox)) -> FileResponse:
    target = file_service.resolve_file(sandbox, path)
    return FileResponse(target)


@router.delete("")
async def delete_file(path: str = Query(...), sandbox=Depends(require_sandbox)) -> dict[str, bool]:
    file_service.delete(sandbox, path)
    return {"ok": True}
