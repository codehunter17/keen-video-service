"""FastAPI entrypoint.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

settings = get_settings()
os.makedirs(settings.output_dir, exist_ok=True)

app = FastAPI(
    title="Keen Video Service",
    version="1.0.0",
    description="Headless automated video generation microservice for Keen.",
)

app.include_router(router)

# Serve rendered MP4s at /files/<job_id>.mp4 (matches output_url in the engine).
app.mount("/files", StaticFiles(directory=settings.output_dir), name="files")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "tts_provider": settings.tts_provider,
        "pexels_configured": bool(settings.pexels_api_key),
        "video_size": list(settings.video_size),
    }
