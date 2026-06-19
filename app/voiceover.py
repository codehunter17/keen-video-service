"""Voiceover generation with word-level timestamps (Hindi-first, with fallback).

Providers are tried in the order given by TTS_CHAIN until one succeeds:
  • edge       — free Microsoft neural TTS (default voice hi-IN-SwaraNeural). Emits
                 WordBoundary events → exact per-word start/end times.
  • elevenlabs — premium paid fallback via the with-timestamps endpoint (per-char
                 alignment folded into words). Used when edge fails (e.g. 403).

Both yield the per-word timings that drive dynamic clip cuts and word-by-word
captions, so the rest of the pipeline is provider-agnostic.
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
def _elevenlabs_tts(text: str, out_path: str) -> list[WordTiming]:
    s = get_settings()
    if not s.elevenlabs_api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is unset")

    resp = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{s.elevenlabs_voice_id}/with-timestamps",
        headers={"xi-api-key": s.elevenlabs_api_key, "Content-Type": "application/json"},
        json={
            "text": text,
            "model_id": s.elevenlabs_model,
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.8,
                "style": 0.3,
                "use_speaker_boost": True,
            },
        },
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
    """Render the voiceover to `out_path` (mp3) and return (path, word timings).

    Providers in TTS_CHAIN are tried in order until one succeeds, so a transient
    failure (e.g. edge-tts returning 403 on a datacenter IP) transparently falls
    back to the next provider instead of failing the whole render.
    """
    s = get_settings()
    errors: list[str] = []
    for provider in s.tts_chain_list:
        try:
            if provider == "edge":
                voice = voice_id or s.edge_default_voice
                timings = asyncio.run(_edge_tts(text, voice, out_path))
            elif provider == "elevenlabs":
                timings = _elevenlabs_tts(text, out_path)
            else:
                log.warning("unknown TTS provider %r in TTS_CHAIN; skipping", provider)
                continue
        except Exception as exc:  # noqa: BLE001 — fall through to the next provider
            log.warning("TTS provider %r failed, falling through: %s", provider, exc)
            errors.append(f"{provider}: {exc}")
            continue

        if not timings:
            log.warning("%s returned no word timings; captions/pacing approximate", provider)
        log.info(
            "voiceover via %s: %d words, %.1fs",
            provider, len(timings), timings[-1].end if timings else 0.0,
        )
        return out_path, timings

    raise RuntimeError(
        "all TTS providers failed -> " + " | ".join(errors)
        if errors else "TTS_CHAIN is empty — no voiceover provider configured"
    )
