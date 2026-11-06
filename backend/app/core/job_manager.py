"""Background job manager for long-running analyses.

Analyses that may take a while (frame extraction, deep scans, big
spectrograms) run on a bounded thread pool. Each job exposes live progress
and a final result or error. Jobs are polled by the frontend.
"""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Job:
    id: str
    kind: str
    status: str = "queued"          # queued | running | done | error | cancelled
    progress: float = 0.0           # 0..1
    message: str = ""
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    meta: dict = field(default_factory=dict)

    def public(self) -> dict:
        d = asdict(self)
        # result can be large; callers fetch it explicitly via result endpoint
        d["has_result"] = self.result is not None
        return d


class ProgressHandle:
    """Passed into job functions so they can report progress and cancellation."""

    def __init__(self, job: "Job", manager: "JobManager"):
        self._job = job
        self._manager = manager

    def update(self, progress: Optional[float] = None, message: Optional[str] = None) -> None:
        if progress is not None:
            self._job.progress = max(0.0, min(1.0, float(progress)))
        if message is not None:
            self._job.message = message

    @property
    def cancelled(self) -> bool:
        return self._manager.is_cancelled(self._job.id)

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled()


class JobCancelled(Exception):
    pass


class JobManager:
    def __init__(self, max_workers: int = 4) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="stego-job")
        self._jobs: dict[str, Job] = {}
        self._cancel: set[str] = set()
        self._lock = threading.RLock()

    def submit(self, kind: str, fn: Callable[[ProgressHandle], Any], meta: Optional[dict] = None) -> Job:
        job = Job(id=uuid.uuid4().hex, kind=kind, meta=meta or {})
        with self._lock:
            self._jobs[job.id] = job
        handle = ProgressHandle(job, self)

        def runner() -> None:
            job.status = "running"
            job.started_at = time.time()
            try:
                job.result = fn(handle)
                job.progress = 1.0
                job.status = "done"
            except JobCancelled:
                job.status = "cancelled"
                job.error = "Cancelled by user"
            except Exception as e:  # noqa: BLE001 - we surface the message
                job.status = "error"
                job.error = f"{type(e).__name__}: {e}"
                job.meta["traceback"] = traceback.format_exc()
            finally:
                job.finished_at = time.time()
                with self._lock:
                    self._cancel.discard(job.id)

        self._pool.submit(runner)
        return job

    def run_sync(self, kind: str, fn: Callable[[ProgressHandle], Any], meta: Optional[dict] = None) -> Job:
        """Run immediately (for fast operations) but return a Job for uniformity."""
        job = Job(id=uuid.uuid4().hex, kind=kind, meta=meta or {}, status="running",
                  started_at=time.time())
        with self._lock:
            self._jobs[job.id] = job
        handle = ProgressHandle(job, self)
        try:
            job.result = fn(handle)
            job.progress = 1.0
            job.status = "done"
        except Exception as e:  # noqa: BLE001
            job.status = "error"
            job.error = f"{type(e).__name__}: {e}"
            job.meta["traceback"] = traceback.format_exc()
        finally:
            job.finished_at = time.time()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._jobs and self._jobs[job_id].status in ("queued", "running"):
                self._cancel.add(job_id)
                return True
        return False

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancel

    def list(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def purge(self, older_than_seconds: int = 7200) -> int:
        now = time.time()
        removed = 0
        with self._lock:
            for jid in list(self._jobs):
                j = self._jobs[jid]
                if j.finished_at and now - j.finished_at > older_than_seconds:
                    del self._jobs[jid]
                    removed += 1
        return removed


jobs = JobManager()
