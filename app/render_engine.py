"""The render engine — orchestrates the whole job.

scene mapping → voiceover (+ word timings) → dynamic scene timing → Pexels
footage per scene → cover-fit + cut to the audio → word-by-word captions →
mux audio → compressed H.264 MP4. Each phase updates the job store so the
/status endpoint reflects real progress.

Dynamic pacing: scene boundaries come from the voiceover's word timings, so a
clip cuts exactly when its sentence finishes speaking — never a static 3s cut.
"""

from __future__ import annotations

import logging
import os
import traceback

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    VideoFileClip,
    afx,
    concatenate_videoclips,
    vfx,
)

from .captions import build_caption_clips
from .config import get_settings
from .jobs import update_job
from .media_fetcher import fetch_clip
from .models import JobState, VideoRequest
from .scene_mapper import Scene, map_scenes
from .voiceover import WordTiming, generate_voiceover

log = logging.getLogger("render_engine")


def _scene_spans(scenes: list[Scene], timings: list[WordTiming], total: float) -> list[tuple[float, float]]:
    """Assign each scene a [start, end] window by consuming its words from the
    sequential word timings — so cuts land on sentence ends."""
    spans: list[tuple[float, float]] = []
    cursor = 0
    n = len(timings)
    for i, scene in enumerate(scenes):
        if not timings:
            # No timings → even split across total duration.
            start = total * i / len(scenes)
            end = total * (i + 1) / len(scenes)
            spans.append((start, end))
            continue
        start_idx = min(cursor, n - 1)
        cursor = min(cursor + max(1, scene.word_count), n)
        is_last = i == len(scenes) - 1
        start = timings[start_idx].start
        end = total if is_last else timings[min(cursor, n - 1)].start
        spans.append((start, max(end, start + 0.4)))
    return spans


def _has_devanagari(text: str) -> bool:
    """True if the text contains any Devanagari codepoint (U+0900–U+097F)."""
    return any("ऀ" <= c <= "ॿ" for c in text)


def _estimate_word_timings(text: str, total: float) -> list[WordTiming]:
    """Evenly distribute `total` seconds across words (weighted by length).

    Used when the TTS provider returns no per-word alignment — notably ElevenLabs
    for Devanagari/Hindi — so captions still render (showing the original script)
    instead of being skipped entirely.
    """
    words = text.split()
    if not words or total <= 0:
        return []
    weights = [max(1, len(w)) for w in words]
    tot = sum(weights)
    timings: list[WordTiming] = []
    t = 0.0
    for w, wt in zip(words, weights):
        dur = total * wt / tot
        timings.append(WordTiming(w, t, t + dur))
        t += dur
    return timings


def _fit_to_frame(clip: VideoFileClip, w: int, h: int):
    """Scale a clip to *cover* the target frame, then centre-crop to exactly w×h."""
    cw, ch = clip.size
    scale = max(w / cw, h / ch)
    clip = clip.with_effects([vfx.Resize(new_size=(round(cw * scale), round(ch * scale)))])
    return clip.with_effects([vfx.Crop(x_center=clip.w // 2, y_center=clip.h // 2, width=w, height=h)])


def _clip_for_span(path: str | None, duration: float, size: tuple[int, int]):
    w, h = size
    if not path or not os.path.exists(path):
        return ColorClip(size=size, color=(18, 18, 24)).with_duration(duration)
    try:
        raw = VideoFileClip(path, audio=False)
        fitted = _fit_to_frame(raw, w, h)
        if fitted.duration >= duration:
            return fitted.subclipped(0, duration)
        return fitted.with_effects([vfx.Loop(duration=duration)])
    except Exception as e:  # noqa: BLE001
        log.warning("clip load failed for %s (%s); using solid bg", path, e)
        return ColorClip(size=size, color=(18, 18, 24)).with_duration(duration)


def _mix_bgm(voice: AudioFileClip, bgm_style: str, total: float):
    """Duck a royalty-free track under the voiceover, if one exists for the style.

    Looks for {bgm_dir}/{bgm_style}.mp3. Missing/failed => return voice unchanged,
    so a missing track never fails the job.
    """
    s = get_settings()
    if not bgm_style or bgm_style.lower() in ("none", "off", ""):
        return voice, None
    path = os.path.join(s.bgm_dir, f"{bgm_style}.mp3")
    if not os.path.exists(path):
        log.info("no BGM track at %s; skipping music", path)
        return voice, None
    try:
        bgm = AudioFileClip(path)
        if bgm.duration < total:
            bed = bgm.with_effects([afx.AudioLoop(duration=total)])
        else:
            bed = bgm.subclipped(0, total)
        bed = bed.with_volume_scaled(s.bgm_volume)
        return CompositeAudioClip([voice, bed]).with_duration(total), bgm
    except Exception as e:  # noqa: BLE001
        log.warning("BGM mix failed (%s); using voice only", e)
        return voice, None


def run_render_job(job_id: str, req: VideoRequest) -> None:
    s = get_settings()
    work = os.path.join(s.work_dir, job_id)
    os.makedirs(work, exist_ok=True)
    os.makedirs(s.output_dir, exist_ok=True)
    open_clips = []

    try:
        # 1. Scenes + descriptive visual prompts.
        update_job(job_id, state=JobState.MAPPING, progress=0.05, message="mapping scenes")
        scenes = map_scenes(req.topic_or_script)
        if not scenes:
            raise ValueError("script produced no scenes")

        # 2. Voiceover + word timings (the script is the full narration).
        update_job(job_id, state=JobState.VOICING, progress=0.2, message="generating voiceover")
        narration = " ".join(sc.text for sc in scenes)
        audio_path = os.path.join(work, "voice.mp3")
        audio_path, timings = generate_voiceover(narration, req.voice_id, audio_path)
        audio = AudioFileClip(audio_path)
        open_clips.append(audio)
        total = audio.duration
        if not timings:
            # Provider gave no alignment (e.g. ElevenLabs for Hindi) → estimate,
            # so word-by-word captions still render the original script.
            timings = _estimate_word_timings(narration, total)
            log.info("no provider timings; estimated %d over %.1fs", len(timings), total)
        elif _has_devanagari(narration) and not _has_devanagari(
            "".join(t.word for t in timings)
        ):
            # ElevenLabs with-timestamps returns per-CHARACTER alignment for
            # Devanagari that reconstructs into mangled word text (caption tofu),
            # even though the audio is correct. The narration itself is clean, so
            # rebuild caption words from it (timing becomes approximate, text right).
            timings = _estimate_word_timings(narration, total)
            log.info("provider alignment lost Devanagari; estimated from narration")
        spans = _scene_spans(scenes, timings, total)

        # 3. Footage per scene (with fallback inside fetch_clip).
        update_job(job_id, state=JobState.FETCHING, progress=0.3, message="fetching footage")
        segments = []
        for i, (scene, (start, end)) in enumerate(zip(scenes, spans)):
            path = fetch_clip(scene.visual_prompt, work, i)
            seg = _clip_for_span(path, max(0.4, end - start), s.video_size)
            segments.append(seg)
            open_clips.append(seg)
            update_job(job_id, progress=0.3 + 0.35 * (i + 1) / len(scenes),
                       message=f"footage {i + 1}/{len(scenes)}")

        # 4. Stitch video, overlay captions, attach audio.
        update_job(job_id, state=JobState.RENDERING, progress=0.7, message="rendering")
        base = concatenate_videoclips(segments, method="compose").with_duration(total)
        caption_clips = build_caption_clips(timings, s.video_size)
        open_clips.extend(caption_clips)
        final = CompositeVideoClip([base, *caption_clips], size=s.video_size)
        mixed_audio, bgm_raw = _mix_bgm(audio, req.bgm_style, total)
        if bgm_raw is not None:
            open_clips.extend([mixed_audio, bgm_raw])
        final = final.with_audio(mixed_audio).with_duration(total)
        open_clips.append(final)

        # 5. Export — compressed, high-quality MP4.
        out_path = os.path.join(s.output_dir, f"{job_id}.mp4")
        final.write_videofile(
            out_path,
            fps=s.fps,
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            bitrate="3500k",
            threads=os.cpu_count() or 2,
            temp_audiofile=os.path.join(work, "mux.m4a"),
            remove_temp=True,
            logger=None,
        )

        url = f"{s.public_url}/files/{job_id}.mp4"
        update_job(job_id, state=JobState.DONE, progress=1.0, message="done",
                   output_path=out_path, output_url=url)
        log.info("job %s done → %s", job_id, out_path)

    except Exception as e:  # noqa: BLE001
        log.error("job %s failed: %s\n%s", job_id, e, traceback.format_exc())
        update_job(job_id, state=JobState.FAILED, message="failed", error=str(e))
    finally:
        for c in open_clips:
            try:
                c.close()
            except Exception:  # noqa: BLE001
                pass
