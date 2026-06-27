"""Lumen5-style word-by-word captions, rendered with Pillow.

We group the word timings into short phrase "lines", and for each word emit a
caption frame showing the line with the *currently spoken* word highlighted.
Frames are composited as masked MoviePy ImageClips — no ImageMagick/TextClip
dependency. Returns a list of clips the render engine overlays on the video.
"""

from __future__ import annotations

import glob
import logging
import os

import numpy as np
from moviepy import ImageClip
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


# Glob patterns to *discover* a Devanagari font regardless of its exact filename.
# Distro packaging varies: fonts-noto-core may ship a variable font
# (NotoSansDevanagari[wght].ttf) or per-weight files, so a hardcoded path is
# fragile — these globs find whatever is actually installed.
_DEVANAGARI_GLOBS = [
    "/usr/share/fonts/**/NotoSansDevanagari*.ttf",
    "/usr/share/fonts/**/*Devanagari*.ttf",
    "/usr/share/fonts/**/Lohit-Devanagari*.ttf",
    "/usr/share/fonts/**/Mangal*.ttf",
]


def _discover_devanagari_fonts() -> list[str]:
    """Find installed Devanagari-capable fonts by globbing the system font dirs."""
    found: list[str] = []
    for pat in _DEVANAGARI_GLOBS:
        found.extend(sorted(glob.glob(pat, recursive=True)))
    # Bold first (heavier reads better over footage), de-duplicated, order-stable.
    found.sort(key=lambda p: (0 if "bold" in p.lower() else 1, p))
    seen: set[str] = set()
    return [p for p in found if not (p in seen or seen.add(p))]


# Latin-capable fonts, tried when the caption text has NO Devanagari. The
# Devanagari fonts (Noto Sans Devanagari) do NOT include Latin glyphs, so using
# one for romanized/English captions renders tofu — pick by script instead.
_LATIN_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/Arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _has_devanagari(text: str) -> bool:
    """True if the text contains any Devanagari codepoint (U+0900–U+097F)."""
    return any("ऀ" <= c <= "ॿ" for c in text)


def _load_font(
    size: int, text: str = ""
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Pick the candidate order by script: Devanagari text needs a Devanagari font
    # (Latin fonts → tofu); Latin/English text needs a Latin font (the Devanagari
    # fonts lack Latin glyphs → tofu). CAPTION_FONT, if set, is honoured first only
    # when it matches the text's script.
    env = os.environ.get("CAPTION_FONT", "")
    if _has_devanagari(text):
        candidates = [env, *_discover_devanagari_fonts(), *_FONT_CANDIDATES, *_LATIN_CANDIDATES]
    else:
        candidates = [*_LATIN_CANDIDATES, env, *_discover_devanagari_fonts()]
    for path in candidates:
        if path and os.path.exists(path):
            try:
                font = ImageFont.truetype(path, size)
                log.info("caption font: %s (devanagari=%s)", path, _has_devanagari(text))
                return font
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
    font = _load_font(max(28, int(w / 16)), " ".join(t.word for t in timings))
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
                .with_start(start)
                .with_duration(duration)
                .with_mask(ImageClip(mask, is_mask=True).with_duration(duration))
                .with_position((0, 0))
            )
            clips.append(clip)

    log.info("built %d caption frames across %d lines", len(clips), len(_group_lines(timings)))
    return clips
