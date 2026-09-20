"""Thread-safe in-memory job store.

Deliberately behind a tiny interface (create/get/update) so the v1
BackgroundTasks engine can be swapped for Celery + Redis (or a DB) at scale
without touching the API or render layers — only this module changes.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone

from .config import get_settings
from .models import JobInfo, JobState

log = logging.getLogger("jobs")

_lock = threading.Lock()
_jobs: dict[str, JobInfo] = {}

# --- Daily render counter (cost guard) -----------------------------------------
# Bucketed by UTC date and mirrored to a tiny JSON file so a process restart
# can't reset the spend ceiling mid-day. Lives in work_dir (NOT output_dir,
# which is served publicly at /files/). File I/O is soft-fail: if the disk is
# unwritable the counter still works in-memory, exactly as before.
_render_day = ""
_render_count = 0
_counter_loaded = False


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _counter_path() -> str:
    return os.path.join(get_settings().work_dir, "render_counter.json")


def _load_counter_locked() -> None:
    """Restore today's count from disk once per process. Call with _lock held."""
    global _render_day, _render_count, _counter_loaded
    _counter_loaded = True
    try:
        with open(_counter_path(), encoding="utf-8") as f:
            data = json.load(f)
        _render_day = str(data.get("date", ""))
        _render_count = int(data.get("count", 0))
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001 — a corrupt file must not break renders
        log.warning("render counter load failed (%s); starting fresh", e)


def _save_counter_locked() -> None:
    """Persist the counter atomically. Call with _lock held. Soft-fail."""
    try:
        path = _counter_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"date": _render_day, "count": _render_count}, f)
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001
        log.warning("render counter save failed (%s); count is in-memory only", e)


def reserve_render_slot(limit: int) -> tuple[bool, int]:
    """Atomically count one render against today's quota.

    `limit <= 0` means unlimited. Returns (allowed, count_today). When allowed is
    False the count is unchanged and the caller should reject (HTTP 429).
    """
    global _render_day, _render_count
    if limit <= 0:
        return True, 0
    today = _utc_today()
    with _lock:
        if not _counter_loaded:
            _load_counter_locked()
        if today != _render_day:
            _render_day, _render_count = today, 0
        if _render_count >= limit:
            return False, _render_count
        _render_count += 1
        _save_counter_locked()
        return True, _render_count


def renders_today() -> int:
    """Current render count for today (0 if the bucket has rolled over)."""
    with _lock:
        if not _counter_loaded:
            _load_counter_locked()
        return _render_count if _render_day == _utc_today() else 0


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
