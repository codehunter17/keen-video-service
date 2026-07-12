"""Smoke tests — the regressions that have actually bitten this project.

No network, no TTS credits, no video export: these cover the pure-Python core
(sentence splitting incl. Devanagari '।', word-timing estimation, script-aware
font selection, caption rendering producing visible pixels, the auth gate, and
the persisted render counter). A broken demo render during validation is the
worst-case failure — this is the cheap insurance against it.
"""

from __future__ import annotations

import importlib
import os

import pytest


# ---------------------------------------------------------------- scene mapping

def test_chunk_script_splits_devanagari_sentences():
    from app.scene_mapper import chunk_script

    scenes = chunk_script("पहला वाक्य। दूसरा वाक्य। तीसरा वाक्य।")
    assert len(scenes) == 3
    assert scenes[0] == "पहला वाक्य।"


def test_chunk_script_splits_latin_sentences():
    from app.scene_mapper import chunk_script

    assert len(chunk_script("One sentence. Two now! Is there a third?")) == 3


def test_chunk_script_never_returns_empty_for_nonempty_input():
    from app.scene_mapper import chunk_script

    assert chunk_script("no terminal punctuation here") == ["no terminal punctuation here"]


def test_heuristic_prompt_is_searchable():
    from app.scene_mapper import _heuristic_prompt

    q = _heuristic_prompt("Pregnant woman eating green vegetables at home.")
    assert q.endswith("cinematic 4k")
    assert "pregnant" in q


# ------------------------------------------------------------- caption timings

def test_estimate_word_timings_covers_duration():
    from app.render_engine import _estimate_word_timings

    text = "आयरन के लिए पालक और चना खाओ"
    total = 12.0
    timings = _estimate_word_timings(text, total)
    assert [t.word for t in timings] == text.split()
    assert timings[0].start == 0.0
    assert timings[-1].end == pytest.approx(total)
    # Monotonic, gap-free.
    for a, b in zip(timings, timings[1:]):
        assert b.start == pytest.approx(a.end)


def test_estimate_word_timings_empty_input():
    from app.render_engine import _estimate_word_timings

    assert _estimate_word_timings("", 10.0) == []
    assert _estimate_word_timings("word", 0.0) == []


def test_scene_spans_even_split_without_timings():
    from app.render_engine import _scene_spans
    from app.scene_mapper import Scene

    scenes = [Scene(i, f"s{i}", "q", 2) for i in range(4)]
    spans = _scene_spans(scenes, [], 8.0)
    assert len(spans) == 4
    assert spans[0] == (0.0, 2.0)
    assert spans[-1][1] == pytest.approx(8.0)


# ------------------------------------------------------- captions: fonts/pixels

def test_has_devanagari_detection():
    from app.captions import _has_devanagari

    assert _has_devanagari("PCOD में क्या खाएं")
    assert not _has_devanagari("PCOD diet tips 101")


def _rendered_alpha(text: str) -> int:
    """Render one caption line through the real pipeline; return opaque pixels."""
    from app.captions import _load_font, _render_line

    font = _load_font(60, text)
    rgba = _render_line(text.split(), 0, (1080, 1920), font)
    return int((rgba[:, :, 3] > 0).sum())


def test_render_line_latin_produces_visible_pixels():
    assert _rendered_alpha("EAT RIGHT LIVE BRIGHT") > 500


def test_render_line_devanagari_produces_visible_pixels():
    from app.captions import _discover_devanagari_fonts

    if not _discover_devanagari_fonts():
        pytest.skip("no Devanagari font installed in this environment")
    assert _rendered_alpha("हरी सब्ज़ियाँ खाएं") > 500


# ------------------------------------------------------------------- HTTP layer

def _client(monkeypatch, tmp_path, api_key: str):
    """Build a TestClient against isolated dirs and a chosen API key."""
    from app import config

    monkeypatch.setenv("SERVICE_API_KEY", api_key)
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    config.get_settings.cache_clear()
    import app.main as main

    importlib.reload(main)
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def test_health_has_build_marker(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, api_key="")
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["build"]


def test_generate_video_rejects_missing_key(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, api_key="sekrit")
    resp = client.post(
        "/api/v1/generate-video",
        json={"topic_or_script": "PCOD में सही खाना बहुत ज़रूरी है।"},
    )
    assert resp.status_code == 401


def test_status_unknown_job_is_404(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path, api_key="")
    assert client.get("/api/v1/status/nope").status_code == 404


# ------------------------------------------------------ persisted render counter

def _reset_counter(monkeypatch, tmp_path):
    from app import config, jobs

    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    config.get_settings.cache_clear()
    monkeypatch.setattr(jobs, "_render_day", "")
    monkeypatch.setattr(jobs, "_render_count", 0)
    monkeypatch.setattr(jobs, "_counter_loaded", False)
    return jobs


def test_render_counter_survives_restart(monkeypatch, tmp_path):
    jobs = _reset_counter(monkeypatch, tmp_path)
    assert jobs.reserve_render_slot(5) == (True, 1)
    assert jobs.reserve_render_slot(5) == (True, 2)

    # Simulate a process restart: wipe in-memory state, keep the file.
    monkeypatch.setattr(jobs, "_render_day", "")
    monkeypatch.setattr(jobs, "_render_count", 0)
    monkeypatch.setattr(jobs, "_counter_loaded", False)

    assert jobs.renders_today() == 2
    allowed, count = jobs.reserve_render_slot(5)
    assert (allowed, count) == (True, 3)


def test_render_counter_enforces_limit(monkeypatch, tmp_path):
    jobs = _reset_counter(monkeypatch, tmp_path)
    assert jobs.reserve_render_slot(1) == (True, 1)
    allowed, count = jobs.reserve_render_slot(1)
    assert allowed is False
    assert count == 1


def test_render_counter_unlimited_when_zero(monkeypatch, tmp_path):
    jobs = _reset_counter(monkeypatch, tmp_path)
    assert jobs.reserve_render_slot(0) == (True, 0)
