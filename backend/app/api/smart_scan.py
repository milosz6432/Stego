"""Smart Scan API — runs the orchestrated scan as a background job."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..analysis import smart_scan as engine
from ..core.job_manager import ProgressHandle, jobs
from ..core.storage import storage

router = APIRouter(prefix="/api/smart-scan", tags=["smart-scan"])


class ScanRequest(BaseModel):
    file_id: str
    depth: Literal["quick", "standard", "deep"] = "standard"


@router.post("")
def start_scan(req: ScanRequest):
    sf = storage.get(req.file_id)
    if sf is None:
        raise HTTPException(404, "File not found")

    def work(p: ProgressHandle):
        return engine.run_smart_scan(req.file_id, req.depth, p)

    job = jobs.submit("smart_scan", work, meta={"file_id": req.file_id, "depth": req.depth})
    return {"job_id": job.id}
