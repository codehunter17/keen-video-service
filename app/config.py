"""Central configuration, loaded once from environment / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Media ---
    pexels_api_key: str = ""
    pexels_orientation: str = "portrait"  # portrait | landscape | square

    # --- Scene-mapping LLM (free-first; optional) ---
    groq_api_key: str = ""
    gemini_api_key: str = ""
    scene_llm_model: str = "llama-3.3-70b-versatile"

    # --- Voiceover ---
    tts_provider: str = "edge"  # "edge" | "elevenlabs"
    edge_default_voice: str = "en-US-AriaNeural"
    elevenlabs_api_key: str = ""

    # --- Video ---
    video_width: int = 1080
    video_height: int = 1920
    fps: int = 30
    max_scene_seconds: float = 7.0  # cap a single clip's screen time
    min_scene_seconds: float = 1.2

    # --- Background music ---
    # Royalty-free tracks live at {bgm_dir}/{bgm_style}.mp3 (operator-supplied).
    # Missing file => no music (the request never fails for a missing track).
    bgm_dir: str = "assets/bgm"
    bgm_volume: float = 0.12  # ducked well under the voiceover

    # --- Paths ---
    output_dir: str = "output"
    work_dir: str = "work"

    # --- Networking / auth ---
    request_timeout: float = 30.0
    service_api_key: str = ""  # X-Keen-Key shared secret; empty = open (dev)
    public_base_url: str = "http://localhost:8000"

    @property
    def video_size(self) -> tuple[int, int]:
        return (self.video_width, self.video_height)


@lru_cache
def get_settings() -> Settings:
    return Settings()
