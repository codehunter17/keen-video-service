"""FastAPI entrypoint.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import get_settings
from .jobs import renders_today

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


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    """Landing page. Without a route here, opening the deployment URL (HF Space /
    Cloud Run) lands on a bare 404 — so the service looks 'not open' even though
    it's running. Confirms it's live and links to the interactive API docs."""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Keen Video Service</title>
  <style>
    :root {{ color-scheme: dark; }}
    body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
           font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
           background:#121218; color:#f4f4f6; }}
    .card {{ max-width:560px; padding:2.5rem; text-align:center; }}
    .dot {{ display:inline-block; width:.6rem; height:.6rem; border-radius:50%;
           background:#3ddc84; margin-right:.4rem; vertical-align:middle; }}
    h1 {{ font-size:1.6rem; margin:.4rem 0 .2rem; }}
    p {{ color:#a9a9b6; line-height:1.5; }}
    .links {{ margin-top:1.6rem; display:flex; gap:.75rem; justify-content:center; flex-wrap:wrap; }}
    a.btn {{ text-decoration:none; padding:.6rem 1.1rem; border-radius:.6rem;
            background:#2d2d3a; color:#f4f4f6; font-weight:600; }}
    a.btn.primary {{ background:#5b5bf0; }}
    code {{ background:#23232e; padding:.15rem .4rem; border-radius:.3rem; font-size:.9em; }}
  </style>
</head>
<body>
  <div class="card">
    <p><span class="dot"></span>Service is running</p>
    <h1>Keen Video Service</h1>
    <p>Headless automated video generation microservice.
       Renders {settings.video_width}&times;{settings.video_height} (9:16) reels via
       <code>POST /api/v1/generate-video</code>.</p>
    <div class="links">
      <a class="btn primary" href="/docs">API Docs</a>
      <a class="btn" href="/health">Health</a>
    </div>
  </div>
</body>
</html>"""


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "build": "captions-from-narration",
        "tts_provider": settings.tts_provider,
        "pexels_configured": bool(settings.pexels_api_key),
        "video_size": list(settings.video_size),
        "max_renders_per_day": settings.max_renders_per_day,
        "renders_today": renders_today(),
    }
