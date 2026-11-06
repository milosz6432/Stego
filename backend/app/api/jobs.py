"""Job polling API for long-running analyses."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.job_manager import jobs

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("")
def list_jobs():
    return [j.public() for j in jobs.list()]


@router.get("/{job_id}")
def get_job(job_id: str):
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(404, "Job not found")
    return j.public()


@router.get("/{job_id}/result")
def job_result(job_id: str):
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(404, "Job not found")
    if j.status == "error":
        raise HTTPException(500, j.error or "Job failed")
    if j.status != "done":
        raise HTTPException(409, f"Job not finished (status={j.status})")
    return j.result


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str):
    ok = jobs.cancel(job_id)
    if not ok:
        raise HTTPException(409, "Job not cancellable")
    return {"cancelled": True}
