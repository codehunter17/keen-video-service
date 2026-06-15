"""Request/response schemas and the job model shared across the service."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class VideoRequest(BaseModel):
    """Payload Keen (the Node backend) posts to /api/v1/generate-video."""

    topic_or_script: str = Field(min_length=3, max_length=8000)
    voice_id: str = "en-US-AriaNeural"
    bgm_style: str = "none"


class JobState(str, Enum):
    QUEUED = "queued"
    MAPPING = "mapping_scenes"
    VOICING = "generating_voiceover"
    FETCHING = "fetching_media"
    RENDERING = "rendering"
    DONE = "done"
    FAILED = "failed"


class JobInfo(BaseModel):
    job_id: str
    state: JobState = JobState.QUEUED
    progress: float = 0.0  # 0.0 → 1.0
    message: str = "queued"
    output_path: str | None = None
    output_url: str | None = None
    error: str | None = None


class CreateJobResponse(BaseModel):
    job_id: str
    state: JobState
    status_url: str
