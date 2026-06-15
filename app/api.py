"""API bridge between Keen (Node) and the render engine.

POST /api/v1/generate-video  → validate, create a job, kick off async render,
                                return job_id immediately.
GET  /api/v1/status/{job_id} → current state / progress / output URL.

Background processing uses FastAPI BackgroundTasks for v1. The job store
(jobs.py) is abstracted so this can move to Celery + Redis without changing
this layer.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from .config import get_settings
from .jobs import create_job, get_job
from .models import CreateJobResponse, JobInfo, VideoRequest
from .render_engine import run_render_job

log = logging.getLogger("api")
router = APIRouter(prefix="/api/v1")


def _check_auth(x_keen_key: str | None) -> None:
    """Shared-secret gate so only Keen can trigger renders. Empty key = open (dev)."""
    expected = get_settings().service_api_key
    if expected and x_keen_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-Keen-Key")


@router.post("/generate-video", response_model=CreateJobResponse, status_code=202)
def generate_video(
    req: VideoRequest,
    background: BackgroundTasks,
    x_keen_key: str | None = Header(default=None),
) -> CreateJobResponse:
    _check_auth(x_keen_key)

    job = create_job()
    background.add_task(run_render_job, job.job_id, req)
    log.info("queued job %s (voice=%s, bgm=%s)", job.job_id, req.voice_id, req.bgm_style)

    return CreateJobResponse(
        job_id=job.job_id,
        state=job.state,
        status_url=f"/api/v1/status/{job.job_id}",
    )


@router.get("/status/{job_id}", response_model=JobInfo)
def job_status(job_id: str) -> JobInfo:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job
