"""Pexels stock-footage fetching with robust fallback.

fetch_clip() searches Pexels for a watermark-free HD clip matching a visual
prompt. If the prompt returns nothing, it automatically broadens the query
(fewer/simpler keywords) and finally falls back to a generic evergreen query,
so a scene is *never* left without footage. Handles 429 rate limits with
bounded backoff.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from .config import get_settings

log = logging.getLogger("media_fetcher")

_PEXELS_SEARCH = "https://api.pexels.com/videos/search"
_GENERIC_FALLBACKS = ["abstract background", "nature landscape", "city timelapse"]
_MAX_RETRIES_429 = 3


def _search(query: str, per_page: int = 12) -> list[dict]:
    s = get_settings()
    if not s.pexels_api_key:
        raise RuntimeError("PEXELS_API_KEY is not set")

    params = {
        "query": query,
        "per_page": per_page,
        "orientation": s.pexels_orientation,
        "size": "medium",  # 'medium' surfaces plenty of HD 1080p without 4k bloat
    }
    headers = {"Authorization": s.pexels_api_key}

    for attempt in range(_MAX_RETRIES_429):
        resp = httpx.get(
            _PEXELS_SEARCH, params=params, headers=headers, timeout=s.request_timeout
        )
        if resp.status_code == 429:
            wait = 2 ** attempt
            log.warning("Pexels 429 rate-limited; backing off %ss", wait)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json().get("videos", [])
    log.error("Pexels still rate-limited after %d retries", _MAX_RETRIES_429)
    return []


def _broaden(query: str) -> str | None:
    """Drop trailing qualifiers/words to widen the search. None when exhausted."""
    words = query.split()
    if len(words) <= 1:
        return None
    return " ".join(words[: max(1, len(words) - 2)])


def _pick_best_file(video: dict, target_w: int, target_h: int) -> str | None:
    """Choose the HD file whose resolution best covers the target frame."""
    files = [f for f in video.get("video_files", []) if f.get("link")]
    if not files:
        return None

    def score(f: dict) -> tuple[int, int]:
        w, h = f.get("width") or 0, f.get("height") or 0
        # Prefer files that meet/exceed the target (so we downscale, never upscale),
        # then the smallest such file to keep downloads lean.
        covers = 1 if (w >= target_w and h >= target_h) else 0
        return (covers, -(w * h) if covers else (w * h))

    files.sort(key=score, reverse=True)
    return files[0]["link"]


def _download(url: str, dest_path: str, timeout: float) -> str:
    with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as fh:
            for chunk in r.iter_bytes(chunk_size=1 << 16):
                fh.write(chunk)
    return dest_path


def fetch_clip(visual_prompt: str, dest_dir: str, index: int) -> str | None:
    """Return a local path to a downloaded HD clip, or None if all attempts fail."""
    s = get_settings()
    os.makedirs(dest_dir, exist_ok=True)
    tw, th = s.video_size

    # Build the ordered list of queries to try: the prompt, progressively
    # broadened versions, then generic evergreen fallbacks.
    queries: list[str] = []
    q: str | None = visual_prompt
    while q:
        queries.append(q)
        q = _broaden(q)
    queries.extend(_GENERIC_FALLBACKS)

    for query in queries:
        try:
            videos = _search(query)
        except Exception as e:  # noqa: BLE001
            log.warning("Pexels search failed for '%s': %s", query, e)
            continue
        if not videos:
            log.info("0 results for '%s' → broadening", query)
            continue
        for video in videos:
            link = _pick_best_file(video, tw, th)
            if not link:
                continue
            dest = os.path.join(dest_dir, f"clip_{index:03d}.mp4")
            try:
                _download(link, dest, s.request_timeout)
                log.info("scene %d footage: '%s' → %s", index, query, dest)
                return dest
            except Exception as e:  # noqa: BLE001
                log.warning("download failed (%s); trying next result", e)
                continue

    log.error("No footage found for scene %d (prompt='%s')", index, visual_prompt)
    return None
