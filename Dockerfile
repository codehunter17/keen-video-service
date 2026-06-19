# Keen Video Service — Hugging Face Space (Docker SDK).
#
# HF runs the container as UID 1000, so we create a matching "user" and keep all
# app files + writable dirs under its home (HF "Permissions" guide). FFmpeg + the
# caption font are installed as root *before* switching user (apt needs root).
FROM python:3.12-slim

# --- System deps (root): FFmpeg for rendering + caption fonts ---
# fonts-noto-core ships Noto Sans Devanagari (Bold) so Hindi/Hinglish captions
# render instead of tofu boxes; fonts-dejavu-core stays as a Latin fallback.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

# --- Non-root user expected by HF Spaces (UID 1000) ---
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH
WORKDIR $HOME/app

# --- Python deps (installed as the runtime user → wheels land in ~/.local) ---
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# --- App code + assets, owned by the runtime user ---
COPY --chown=user app ./app
COPY --chown=user assets ./assets

# Writable dirs for renders (owned by user so runtime writes succeed under UID 1000).
RUN mkdir -p output work

# Caption font baked into the image — Devanagari-capable for Hindi/Hinglish.
# Secrets/vars (PEXELS_API_KEY, SERVICE_API_KEY, PUBLIC_BASE_URL, ELEVENLABS_API_KEY,
# TTS_CHAIN, …) are injected by HF at runtime — never bake them into the image.
ENV CAPTION_FONT=/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf

# HF routes the Space's public URL to this port (must match app_port in README.md).
EXPOSE 8000

# 1 worker: rendering is CPU-bound; scale via more instances / a queue later.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
