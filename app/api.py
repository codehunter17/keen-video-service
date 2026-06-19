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


@router.get("/diag")
def diag(x_keen_key: str | None = Header(default=None)) -> dict:
    """Key-gated ops probe: surfaces which providers are configured and runs a
    live Pexels search + download from *inside* the Space, so footage failures
    (which the render path swallows into a solid-colour fallback) are visible."""
    _check_auth(x_keen_key)
    import os

    from .media_fetcher import _download, _pick_best_file, _search

    s = get_settings()
    out: dict = {
        "pexels_configured": bool(s.pexels_api_key),
        "elevenlabs_configured": bool(s.elevenlabs_api_key),
        "groq_configured": bool(s.groq_api_key),
        "gemini_configured": bool(s.gemini_api_key),
        "tts_chain": s.tts_chain_list,
        "edge_voice": s.edge_default_voice,
        "public_url": s.public_url,
        "space_host": os.environ.get("SPACE_HOST"),
    }
    try:
        vids = _search("lifestyle cinematic 4k", per_page=3)
        out["pexels_search_count"] = len(vids)
        if vids:
            link = _pick_best_file(vids[0], *s.video_size)
            out["pexels_first_link"] = (link or "")[:100]
            try:
                os.makedirs(s.work_dir, exist_ok=True)
                tmp = os.path.join(s.work_dir, "diag_clip.mp4")
                _download(link, tmp, s.request_timeout)
                out["download_ok"] = True
                out["download_size"] = os.path.getsize(tmp)
            except Exception as e:  # noqa: BLE001
                out["download_ok"] = False
                out["download_error"] = f"{type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001
        out["pexels_search_error"] = f"{type(e).__name__}: {e}"
    return out
