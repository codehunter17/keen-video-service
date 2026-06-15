"""Thread-safe in-memory job store.

Deliberately behind a tiny interface (create/get/update) so the v1
BackgroundTasks engine can be swapped for Celery + Redis (or a DB) at scale
without touching the API or render layers — only this module changes.
"""

from __future__ import annotations

import threading
import uuid

from .models import JobInfo, JobState

_lock = threading.Lock()
_jobs: dict[str, JobInfo] = {}


def create_job() -> JobInfo:
    job_id = uuid.uuid4().hex
    info = JobInfo(job_id=job_id, state=JobState.QUEUED)
    with _lock:
        _jobs[job_id] = info
    return info


def get_job(job_id: str) -> JobInfo | None:
    with _lock:
        info = _jobs.get(job_id)
        # Return a copy so callers can't mutate the stored object directly.
        return info.model_copy() if info else None


def update_job(
    job_id: str,
    *,
    state: JobState | None = None,
    progress: float | None = None,
    message: str | None = None,
    output_path: str | None = None,
    output_url: str | None = None,
    error: str | None = None,
) -> None:
    with _lock:
        info = _jobs.get(job_id)
        if not info:
            return
        if state is not None:
            info.state = state
        if progress is not None:
            info.progress = max(0.0, min(1.0, progress))
        if message is not None:
            info.message = message
        if output_path is not None:
            info.output_path = output_path
        if output_url is not None:
            info.output_url = output_url
        if error is not None:
            info.error = error
