"""Upload, listing and download of files (originals and recovered payloads)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response

from ..core import config
from ..core.file_detection import detect_file
from ..core.storage import storage
from ..core.util import hex_dump, b64, find_text_strings

router = APIRouter(prefix="/api/files", tags=["files"])


def _file_info(sf) -> dict:
    det = detect_file(sf.stored_path)
    return {
        "id": sf.id,
        "name": sf.name,
        "size": sf.size,
        "sha256": sf.sha256,
        "media_type": sf.media_type,
        "format": sf.format,
        "mime": sf.mime,
        "origin": sf.origin,
        "parent_id": sf.parent_id,
        "created_at": sf.created_at,
        "meta": sf.meta,
        "detection": {
            "media_type": det.media_type,
            "format": det.format,
            "description": det.description,
            "confidence": det.confidence,
            "extension": det.extension,
            "applicable_modules": det.applicable_modules,
        },
    }


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    try:
        sf = storage.store_stream(file.file, file.filename, origin="upload")
    except ValueError as e:
        raise HTTPException(413, str(e))
    return _file_info(sf)


@router.get("")
def list_files():
    return [_file_info(sf) for sf in storage.list()]


@router.get("/{file_id}")
def get_file(file_id: str):
    sf = storage.get(file_id)
    if sf is None:
        raise HTTPException(404, "File not found")
    return _file_info(sf)


@router.get("/{file_id}/download")
def download(file_id: str):
    sf = storage.get(file_id)
    if sf is None:
        raise HTTPException(404, "File not found")
    return FileResponse(sf.stored_path, filename=sf.name, media_type=sf.mime)


@router.get("/{file_id}/raw")
def raw(file_id: str):
    """Serve bytes inline (for <img>/<audio>/<video> previews)."""
    sf = storage.get(file_id)
    if sf is None:
        raise HTTPException(404, "File not found")
    data = open(sf.stored_path, "rb").read()
    return Response(content=data, media_type=sf.mime)


@router.get("/{file_id}/hex")
def hexview(file_id: str, offset: int = 0, length: int = 4096):
    sf = storage.get(file_id)
    if sf is None:
        raise HTTPException(404, "File not found")
    length = max(0, min(length, 1 << 20))
    with open(sf.stored_path, "rb") as f:
        f.seek(offset)
        data = f.read(length)
    return {
        "offset": offset,
        "length": len(data),
        "total": sf.size,
        "rows": hex_dump(data, offset=offset),
        "base64": b64(data),
    }


@router.get("/{file_id}/strings")
def strings(file_id: str, min_len: int = 4):
    sf = storage.get(file_id)
    if sf is None:
        raise HTTPException(404, "File not found")
    data = open(sf.stored_path, "rb").read(16 * 1024 * 1024)
    return {"strings": find_text_strings(data, min_len=min_len)}


@router.delete("/{file_id}")
def delete(file_id: str):
    ok = storage.delete(file_id)
    if not ok:
        raise HTTPException(404, "File not found")
    return {"deleted": True}
