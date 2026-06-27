"""Central configuration, loaded once from environment / .env."""

from __future__ import annotations

import os
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

    # --- Voiceover (fallback chain) ---
    # Providers are tried left→right until one succeeds, so a transient failure
    # (e.g. edge-tts 403 from a datacenter IP) auto-falls-back instead of failing
    # the whole render. Providers: "edge" (free Microsoft neural) | "elevenlabs".
    tts_chain: str = ""              # e.g. "edge,elevenlabs"; empty => derived below
    tts_provider: str = "edge"       # DEPRECATED; only used when tts_chain is empty
    edge_default_voice: str = "hi-IN-SwaraNeural"      # warm Hindi female (free)
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "o6qTxWUeRyzRYZyUNDVJ"  # multilingual female (Hindi-capable)
    elevenlabs_model: str = "eleven_flash_v2_5"        # supports Hindi

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
    public_base_url: str = ""  # explicit override; empty => auto from SPACE_HOST (HF)

    # --- Cost guard ---
    # Hard ceiling on renders accepted per UTC day. Each render costs an ElevenLabs
    # call (edge is IP-blocked on HF) + CPU, so this caps spend if the endpoint is
    # abused or a caller loops. Exceeding it returns HTTP 429. Defaults to a safe
    # non-zero ceiling so a forgotten env var can't mean unbounded spend; set
    # MAX_RENDERS_PER_DAY=0 explicitly to opt into unlimited (local/dev only).
    max_renders_per_day: int = 50

    @property
    def video_size(self) -> tuple[int, int]:
        return (self.video_width, self.video_height)

    @property
    def public_url(self) -> str:
        """Base URL for serving rendered files. Prefers an explicit setting, else
        auto-detects the HF Space host (HF sets SPACE_HOST), else localhost."""
        if self.public_base_url:
            return self.public_base_url.rstrip("/")
        host = os.environ.get("SPACE_HOST")  # e.g. keenhunter-keen-video-service.hf.space
        if host:
            return f"https://{host.rstrip('/')}"
        return "http://localhost:8000"

    @property
    def tts_chain_list(self) -> list[str]:
        """Ordered list of TTS providers to try. Falls back from TTS_PROVIDER."""
        raw = self.tts_chain.strip()
        if raw:
            return [p.strip().lower() for p in raw.split(",") if p.strip()]
        # Back-compat: honor a lone TTS_PROVIDER, else free-first with paid fallback.
        return (
            ["elevenlabs", "edge"]
            if self.tts_provider.strip().lower() == "elevenlabs"
            else ["edge", "elevenlabs"]
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
