# Keen Video Service

A headless, asynchronous video-generation microservice. Keen (the Node backend)
posts a topic/script; this service renders a Lumen5-style stock-footage video
with voiceover and word-by-word captions, and exposes a status endpoint.

```
keen-video-service/
├── requirements.txt
├── .env.example          → copy to .env
└── app/
    ├── main.py           # FastAPI app + static file serving
    ├── api.py            # POST /generate-video, GET /status/{id}
    ├── config.py         # settings (env)
    ├── models.py         # request/response + job schemas
    ├── jobs.py           # thread-safe job store (Celery-ready interface)
    ├── scene_mapper.py   # script → scenes + descriptive visual prompts (LLM)
    ├── media_fetcher.py  # Pexels HD fetch + broaden/generic fallback
    ├── voiceover.py      # Edge-TTS / ElevenLabs + word-level timestamps
    ├── captions.py       # Lumen5 word-by-word captions (PIL → ImageClip)
    └── render_engine.py  # orchestration + dynamic pacing + FFmpeg export
```

## Pipeline
`scene mapping → voiceover (+word timings) → dynamic scene timing → Pexels
footage (with fallback) → cover-fit + cut to the audio → word-by-word captions
→ mux audio → compressed H.264 MP4`. Scene cuts are driven by the voiceover's
word timings, so clips transition on sentence ends — not static 3s cuts.

## Prerequisites
- **Python 3.10+**
- **FFmpeg installed at the OS level** (`ffmpeg -version`). `imageio-ffmpeg`
  bundles a fallback binary, but a system FFmpeg is recommended.
- A **Pexels API key** (free): https://www.pexels.com/api/
- Optional: a **Groq** or **Gemini** key for rich visual prompts (falls back to
  a keyword heuristic). ElevenLabs key only if `TTS_PROVIDER=elevenlabs`.

## Run
```bash
cd keen-video-service
python -m venv .venv && . .venv/Scripts/activate   # Windows
# source .venv/bin/activate                         # macOS/Linux
pip install -r requirements.txt
cp .env.example .env        # then set PEXELS_API_KEY (+ optional keys)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Test
```bash
# 1. enqueue
curl -s -X POST http://localhost:8000/api/v1/generate-video \
  -H "Content-Type: application/json" \
  -d '{"topic_or_script":"Iron is vital in pregnancy. Eat dates, spinach and jaggery daily. See a doctor if you feel very tired.","voice_id":"en-US-AriaNeural","bgm_style":"none"}'
# → {"job_id":"...","state":"queued","status_url":"/api/v1/status/..."}

# 2. poll
curl -s http://localhost:8000/api/v1/status/<job_id>
# 3. when state=done, the MP4 is at output_url (served from /files/<job_id>.mp4)
```

## Calling it from Keen (Node)
```ts
// fire-and-forget enqueue, then poll status_url until state === "done"
const res = await fetch(`${VIDEO_SERVICE_URL}/api/v1/generate-video`, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-Keen-Key": process.env.VIDEO_SERVICE_KEY ?? "" },
  body: JSON.stringify({ topic_or_script: script, voice_id: "en-US-AriaNeural", bgm_style: "none" }),
});
const { job_id, status_url } = await res.json();
```

## Background music
Drop royalty-free tracks at `assets/bgm/<bgm_style>.mp3` (e.g. `chill.mp3`).
A request with `"bgm_style":"chill"` ducks `chill.mp3` under the voiceover at
`BGM_VOLUME` (default 0.12). Missing file → voiceover only (never fails). See
`assets/bgm/README.md`. The service ships no copyrighted audio.

## Deployment notes
- **Not Vercel.** Renders take minutes and need FFmpeg — host on a container/VM
  (Render, Railway, Fly.io, or a VPS). A `Dockerfile` (FFmpeg + DejaVu bold font
  baked in) is included:
  ```bash
  docker build -t keen-video-service .
  docker run -p 8000:8000 --env-file .env keen-video-service
  ```
- **Scale:** v1 uses FastAPI `BackgroundTasks` (in-process). For throughput, swap
  `jobs.py` + the task dispatch for **Celery + Redis** and run N render workers;
  the API/render layers don't change.
- Set `SERVICE_API_KEY` in production so only Keen can trigger renders.

## Status: reviewed, not yet run
Written against the FFmpeg/MoviePy 1.0.3 + Pillow + edge-tts stack. It needs a
Python env + FFmpeg + a Pexels key to execute end-to-end (not available in the
Node workspace where it was authored). Run the steps above to produce the first
MP4; tuning knobs live in `config.py` / `.env`.
