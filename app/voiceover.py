"""Voiceover generation with word-level timestamps.

Edge-TTS (free) emits WordBoundary events as it streams, giving us exact
per-word start/end times — the basis for both dynamic clip cuts and word-by-word
captions. ElevenLabs is supported via its with-timestamps endpoint when chosen.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass

import edge_tts
import httpx

from .config import get_settings

log = logging.getLogger("voiceover")


@dataclass
class WordTiming:
    word: str
    start: float  # seconds
    end: float


# ── Edge-TTS ──────────────────────────────────────────────────────────────────
async def _edge_tts(text: str, voice: str, out_path: str) -> list[WordTiming]:
    communicate = edge_tts.Communicate(text, voice)
    timings: list[WordTiming] = []
    with open(out_path, "wb") as fh:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                fh.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # edge-tts reports offset/duration in 100-nanosecond ticks.
                start = chunk["offset"] / 1e7
                dur = chunk["duration"] / 1e7
                timings.append(WordTiming(chunk["text"], start, start + dur))
    return timings


# ── ElevenLabs ──────────────────────────────────────────────────────────────-
def _elevenlabs_tts(text: str, voice_id: str, out_path: str) -> list[WordTiming]:
    s = get_settings()
    if not s.elevenlabs_api_key:
        raise RuntimeError("TTS_PROVIDER=elevenlabs but ELEVENLABS_API_KEY is unset")

    resp = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps",
        headers={"xi-api-key": s.elevenlabs_api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_flash_v2_5"},
        timeout=max(s.request_timeout, 60.0),
    )
    resp.raise_for_status()
    data = resp.json()
    with open(out_path, "wb") as fh:
        fh.write(base64.b64decode(data["audio_base64"]))

    # ElevenLabs returns per-character alignment; fold it into words.
    align = data.get("alignment") or data.get("normalized_alignment") or {}
    chars = align.get("characters", [])
    starts = align.get("character_start_times_seconds", [])
    ends = align.get("character_end_times_seconds", [])
    return _chars_to_words(chars, starts, ends)


def _chars_to_words(
    chars: list[str], starts: list[float], ends: list[float]
) -> list[WordTiming]:
    timings: list[WordTiming] = []
    buf, w_start, w_end = "", None, None
    for ch, st, en in zip(chars, starts, ends):
        if ch.isspace():
            if buf:
                timings.append(WordTiming(buf, w_start or 0.0, w_end or 0.0))
                buf, w_start, w_end = "", None, None
        else:
            if w_start is None:
                w_start = st
            buf += ch
            w_end = en
    if buf:
        timings.append(WordTiming(buf, w_start or 0.0, w_end or 0.0))
    return timings


def generate_voiceover(
    text: str, voice_id: str, out_path: str
) -> tuple[str, list[WordTiming]]:
    """Render the voiceover to `out_path` (mp3) and return (path, word timings)."""
    s = get_settings()
    if s.tts_provider == "elevenlabs":
        timings = _elevenlabs_tts(text, voice_id, out_path)
    else:
        voice = voice_id or s.edge_default_voice
        timings = asyncio.run(_edge_tts(text, voice, out_path))

    if not timings:
        log.warning("no word timings returned; captions/pacing will be approximate")
    log.info("voiceover: %d words, %.1fs", len(timings), timings[-1].end if timings else 0)
    return out_path, timings
