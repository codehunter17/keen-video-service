# Keen Video Service — Python 3.12 (best wheel compatibility for moviepy 1.0.3).
FROM python:3.12-slim

# FFmpeg (rendering) + a bold TrueType font (captions fall back to DejaVu).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY assets ./assets

ENV CAPTION_FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
EXPOSE 8000

# 1 worker: rendering is CPU-bound; scale by running more containers / a queue.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
