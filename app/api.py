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
from .jobs import create_job, get_job, renders_today, reserve_render_slot
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

    # Cost guard: cap renders/day (each costs an ElevenLabs call + CPU).
    s = get_settings()
    allowed, count = reserve_render_slot(s.max_renders_per_day)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"daily render cap reached ({s.max_renders_per_day}/day); try again tomorrow (UTC)",
        )

    job = create_job()
    background.add_task(run_render_job, job.job_id, req)
    log.info("queued job %s (voice=%s, bgm=%s)", job.job_id, req.voice_id, req.bgm_style)

    return CreateJobResponse(
        job_id=job.job_id,
        state=job.state,
        status_url=f"/api/v1/status/{job.job_id}",
    )


@router.get("/debug-text")
def debug_text(script: str, x_keen_key: str | None = Header(default=None)) -> dict:
    """Dump the caption text flow for a script: the narration, the provider's
    word timings, and the final caption words — so tofu can be traced to its
    source (provider alignment vs narration). Costs one TTS call."""
    _check_auth(x_keen_key)
    import os

    from .scene_mapper import map_scenes
    from .voiceover import generate_voiceover

    scenes = map_scenes(script)
    narration = " ".join(sc.text for sc in scenes)
    tmp = os.path.join(get_settings().work_dir, "debug_voice.mp3")
    os.makedirs(get_settings().work_dir, exist_ok=True)
    _, timings = generate_voiceover(narration, "hi-IN-SwaraNeural", tmp)
    prov = [t.word for t in timings]
    return {
        "narration": narration,
        "narration_words": narration.split(),
        "provider_word_count": len(prov),
        "provider_words_sample": prov[:12],
        "provider_first_word_codepoints": [hex(ord(c)) for c in (prov[0] if prov else "")],
        "matches_narration": prov == narration.split(),
    }


@router.get("/status/{job_id}", response_model=JobInfo)
def job_status(job_id: str) -> JobInfo:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _probe_tts() -> dict:
    """Synthesize a tiny Hindi word through each provider in the chain so it's
    visible which actually work — edge is often IP-blocked on datacenter hosts,
    in which case every render silently (and at cost) falls through to ElevenLabs.
    Note: the ElevenLabs probe costs a few credits per call (it's a real synth)."""
    import asyncio
    import os

    from .voiceover import _edge_tts, _elevenlabs_tts

    s = get_settings()
    os.makedirs(s.work_dir, exist_ok=True)
    results: dict[str, object] = {}
    for provider in s.tts_chain_list:
        tmp = os.path.join(s.work_dir, f"diag_tts_{provider}.mp3")
        try:
            if provider == "edge":
                timings = asyncio.run(_edge_tts("नमस्ते", s.edge_default_voice, tmp))
            elif provider == "elevenlabs":
                timings = _elevenlabs_tts("नमस्ते", tmp)
            else:
                results[provider] = "unknown provider"
                continue
            size = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            results[provider] = {"ok": size > 0, "bytes": size, "words": len(timings)}
        except Exception as e:  # noqa: BLE001
            results[provider] = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return results


def _caption_selftest() -> dict:
    """Render a known-good Devanagari caption through the real caption pipeline
    and save it to output/ so the result is viewable. Isolates whether tofu comes
    from the rendering/font (this will be tofu too) or from upstream LLM text
    (this renders fine, so the text is the culprit)."""
    import os

    from PIL import Image

    from .captions import _load_font, _render_line

    s = get_settings()
    os.makedirs(s.output_dir, exist_ok=True)
    text = "गर्भावस्था में हरी सब्ज़ियाँ खाएं"
    words = text.split()
    font = _load_font(max(28, int(s.video_width / 16)), text)
    rgba = _render_line(words, 1, s.video_size, font)
    Image.fromarray(rgba).convert("RGB").save(os.path.join(s.output_dir, "caption_selftest.png"))
    return {
        "text": text,
        "font_path": getattr(font, "path", None),
        "url": f"{s.public_url}/files/caption_selftest.png",
    }


@router.get("/diag")
def diag(
    tts: int = 0, caption: int = 0, x_keen_key: str | None = Header(default=None)
) -> dict:
    """Key-gated ops probe: surfaces which providers are configured and runs a
    live Pexels search + download from *inside* the Space, so footage failures
    (which the render path swallows into a solid-colour fallback) are visible.
    Pass ?tts=1 to also synth-test each voiceover provider (costs ElevenLabs
    credits)."""
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
        "max_renders_per_day": s.max_renders_per_day,
        "renders_today": renders_today(),
    }
    if tts:
        out["tts_probe"] = _probe_tts()
    if caption:
        try:
            out["caption_selftest"] = _caption_selftest()
        except Exception as e:  # noqa: BLE001
            out["caption_selftest_error"] = f"{type(e).__name__}: {e}"

    # Font diagnostics — explains Devanagari caption tofu (wrong/missing font, or
    # Pillow built without libraqm so complex scripts don't shape).
    try:
        import glob as _glob

        from PIL import ImageFont, features

        from .captions import _discover_devanagari_fonts

        chosen = None
        for p in _discover_devanagari_fonts():
            try:
                ImageFont.truetype(p, 40)
                chosen = p
                break
            except Exception:  # noqa: BLE001
                continue
        out["fonts"] = {
            "raqm_shaping": features.check("raqm"),  # needed to shape Devanagari
            "devanagari_found": _discover_devanagari_fonts(),
            "chosen_devanagari": chosen,
            "ttf_total": len(_glob.glob("/usr/share/fonts/**/*.ttf", recursive=True)),
            "caption_font_env": os.environ.get("CAPTION_FONT"),
        }
    except Exception as e:  # noqa: BLE001
        out["fonts_error"] = f"{type(e).__name__}: {e}"

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
