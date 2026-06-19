"""Lumen5-style word-by-word captions, rendered with Pillow.

We group the word timings into short phrase "lines", and for each word emit a
caption frame showing the line with the *currently spoken* word highlighted.
Frames are composited as masked MoviePy ImageClips — no ImageMagick/TextClip
dependency. Returns a list of clips the render engine overlays on the video.
"""

from __future__ import annotations

import logging
import os

import numpy as np
from moviepy.editor import ImageClip
from PIL import Image, ImageDraw, ImageFont

from .voiceover import WordTiming

log = logging.getLogger("captions")

_MAX_WORDS_PER_LINE = 4
_PAUSE_BREAK = 0.6  # a gap longer than this starts a new line
_BASE_COLOR = (255, 255, 255, 255)
_ACTIVE_COLOR = (255, 214, 10, 255)  # warm yellow highlight
_STROKE_COLOR = (0, 0, 0, 230)

# Devanagari-capable fonts MUST come before Latin-only ones: Hindi/Hinglish
# captions render as tofu (☐☐☐) in DejaVu/Arial. Noto Sans Devanagari also
# covers Latin, so it handles mixed Hinglish lines too. (Pillow's wheels bundle
# libraqm, so Devanagari conjuncts/matras shape correctly.)
_FONT_CANDIDATES = [
    os.environ.get("CAPTION_FONT", ""),
    # — Devanagari (Hindi/Hinglish) —
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    "C:/Windows/Fonts/NirmalaB.ttf",   # Nirmala UI Bold (Windows, Devanagari)
    "C:/Windows/Fonts/Nirmala.ttf",
    # — Latin-only fallbacks (English captions) —
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/Arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if path and os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:  # noqa: BLE001
                continue
    log.warning("no TrueType font found; falling back to PIL default (small)")
    return ImageFont.load_default()


def _group_lines(timings: list[WordTiming]) -> list[list[WordTiming]]:
    lines: list[list[WordTiming]] = []
    cur: list[WordTiming] = []
    for i, w in enumerate(timings):
        if cur:
            gap = w.start - cur[-1].end
            if len(cur) >= _MAX_WORDS_PER_LINE or gap > _PAUSE_BREAK:
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _render_line(
    words: list[str], active: int, size: tuple[int, int], font
) -> np.ndarray:
    """Render a transparent RGBA frame of one caption line, highlighting word `active`."""
    w, h = size
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    gap = max(6, int(font.size * 0.35)) if hasattr(font, "size") else 12
    widths = [draw.textlength(word, font=font) for word in words]
    total = sum(widths) + gap * (len(words) - 1)
    x = (w - total) / 2
    y = int(h * 0.72)  # lower third, reel-friendly

    stroke = max(2, int((getattr(font, "size", 40)) * 0.06))
    for i, word in enumerate(words):
        color = _ACTIVE_COLOR if i == active else _BASE_COLOR
        draw.text(
            (x, y), word, font=font, fill=color,
            stroke_width=stroke, stroke_fill=_STROKE_COLOR,
        )
        x += widths[i] + gap
    return np.array(img)


def build_caption_clips(
    timings: list[WordTiming], video_size: tuple[int, int]
) -> list[ImageClip]:
    """One masked ImageClip per spoken word, timed to the voiceover."""
    if not timings:
        return []

    w, h = video_size
    font = _load_font(max(28, int(w / 16)))
    clips: list[ImageClip] = []

    for line in _group_lines(timings):
        words = [t.word for t in line]
        for i, t in enumerate(line):
            start = t.start
            # Hold each word's frame until the next word begins (no dead air).
            end = line[i + 1].start if i + 1 < len(line) else t.end
            duration = max(0.12, end - start)

            rgba = _render_line(words, i, (w, h), font)
            rgb = rgba[:, :, :3]
            mask = rgba[:, :, 3] / 255.0

            clip = (
                ImageClip(rgb)
                .set_start(start)
                .set_duration(duration)
                .set_mask(ImageClip(mask, ismask=True).set_duration(duration))
                .set_position((0, 0))
            )
            clips.append(clip)

    log.info("built %d caption frames across %d lines", len(clips), len(_group_lines(timings)))
    return clips
