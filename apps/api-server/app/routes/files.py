from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app.deps import get_current_subject, require_sandbox
from app.schemas.common import ApiEnvelope, ok
from app.schemas.files import FileEntry, ReadFileResponse, WriteFileRequest, WriteFileResponse
from app.services.files import file_service

router = APIRouter(prefix="/sandbox/{sandbox_id}/files", tags=["files"], dependencies=[Depends(get_current_subject)])


@router.get("/list", response_model=ApiEnvelope[list[FileEntry]])
async def list_files(path: str = Query("/workspace"), sandbox=Depends(require_sandbox)) -> ApiEnvelope[list[FileEntry]]:
    return ok(file_service.list(sandbox, path))


@router.get("/read", response_model=ApiEnvelope[ReadFileResponse])
async def read_file(path: str = Query(...), sandbox=Depends(require_sandbox)) -> ApiEnvelope[ReadFileResponse]:
    return ok(ReadFileResponse(path=path, content=file_service.read_text(sandbox, path)))


@router.post("/write", response_model=ApiEnvelope[WriteFileResponse])
async def write_file(payload: WriteFileRequest, sandbox=Depends(require_sandbox)) -> ApiEnvelope[WriteFileResponse]:
    target = file_service.write_text(sandbox, payload.path, payload.content, payload.overwrite)
    return ok(WriteFileResponse(path=str(target)), message="file written")


@router.post("/upload", response_model=ApiEnvelope[WriteFileResponse])
async def upload_file(upload: UploadFile = File(...), sandbox=Depends(require_sandbox)) -> ApiEnvelope[WriteFileResponse]:
    target = await file_service.upload(sandbox, upload)
    return ok(WriteFileResponse(path=str(target)), message="file uploaded")


@router.get("/download")
async def download_file(path: str = Query(...), sandbox=Depends(require_sandbox)) -> FileResponse:
    target = file_service.resolve_file(sandbox, path)
    return FileResponse(target)


@router.delete("", response_model=ApiEnvelope[dict[str, bool]])
async def delete_file(path: str = Query(...), sandbox=Depends(require_sandbox)) -> ApiEnvelope[dict[str, bool]]:
    file_service.delete(sandbox, path)
    return ok({"ok": True}, message="file deleted")
