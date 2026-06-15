"""Semantic scene mapping — the 'Keen logic' wrapper.

Turns a raw script into ordered scenes, and for each scene produces a *highly
descriptive visual search prompt* for stock-footage lookup (e.g. not "apple"
but "corporate professional working on laptop, modern office, 4k"). Uses a
free LLM (Groq, or Gemini) when a key is present, and falls back to a
deterministic keyword heuristic so the service works with zero paid keys.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

from .config import get_settings

log = logging.getLogger("scene_mapper")

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+")
# Words too generic to drive good stock footage — dropped by the heuristic.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "of", "to", "in", "on", "for",
    "with", "is", "are", "was", "were", "be", "been", "it", "this", "that",
    "these", "those", "as", "at", "by", "from", "your", "you", "we", "our",
    "they", "their", "can", "will", "may", "have", "has", "had", "do", "does",
    "so", "not", "no", "yes", "than", "then", "into", "about", "over", "more",
}

_VISUAL_SYS = (
    "You convert one sentence of a video script into a single, vivid stock-footage "
    "search query for Pexels. Output ONLY the query (3-7 words), no quotes, no "
    "explanation. Describe a concrete, filmable scene with subject + setting + a "
    "cinematic qualifier (e.g. '4k', 'slow motion', 'aerial'). Prefer literal, "
    "searchable imagery over abstract concepts."
)


@dataclass
class Scene:
    index: int
    text: str
    visual_prompt: str
    word_count: int


def chunk_script(script: str) -> list[str]:
    """Split a script into sentence-level scenes."""
    cleaned = re.sub(r"\s+", " ", script.strip())
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(cleaned) if s.strip()]
    return sentences or ([cleaned] if cleaned else [])


def _heuristic_prompt(sentence: str) -> str:
    """Deterministic fallback: keep the most evocative keywords + a qualifier."""
    words = re.findall(r"[A-Za-z][A-Za-z'-]+", sentence.lower())
    keywords = [w for w in words if w not in _STOPWORDS and len(w) > 2]
    # Keep the first few content words (they usually carry the visual subject).
    picked = keywords[:4] or words[:3] or ["lifestyle"]
    return " ".join(picked) + " cinematic 4k"


def _llm_prompt(sentence: str) -> str | None:
    """Ask a free LLM for a rich visual query. Returns None on any failure."""
    s = get_settings()
    try:
        if s.groq_api_key:
            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
                json={
                    "model": s.scene_llm_model,
                    "temperature": 0.4,
                    "max_tokens": 40,
                    "messages": [
                        {"role": "system", "content": _VISUAL_SYS},
                        {"role": "user", "content": sentence},
                    ],
                },
                timeout=s.request_timeout,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            return _clean_query(text)

        if s.gemini_api_key:
            resp = httpx.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash:generateContent?key={s.gemini_api_key}",
                json={
                    "system_instruction": {"parts": [{"text": _VISUAL_SYS}]},
                    "contents": [{"parts": [{"text": sentence}]}],
                    "generationConfig": {"temperature": 0.4, "maxOutputTokens": 40},
                },
                timeout=s.request_timeout,
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return _clean_query(text)
    except Exception as e:  # noqa: BLE001 — any LLM hiccup → heuristic fallback
        log.warning("visual-prompt LLM failed (%s); using heuristic", e)
    return None


def _clean_query(text: str) -> str:
    q = text.strip().strip('"').strip("'").splitlines()[0]
    q = re.sub(r"[^\w\s-]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q[:80]


def generate_visual_prompt(sentence: str) -> str:
    return _llm_prompt(sentence) or _heuristic_prompt(sentence)


def map_scenes(script: str) -> list[Scene]:
    sentences = chunk_script(script)
    scenes: list[Scene] = []
    for i, text in enumerate(sentences):
        prompt = generate_visual_prompt(text)
        scenes.append(
            Scene(
                index=i,
                text=text,
                visual_prompt=prompt,
                word_count=len(re.findall(r"\S+", text)),
            )
        )
        log.info("scene %d → '%s'", i, prompt)
    return scenes
