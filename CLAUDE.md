# CLAUDE.md — session bootstrap for keen-video-service

**FIRST: read `KNOWLEDGE_GRAPH.md`.** It is this project's persistent memory —
architecture graph, per-file index, env/config map, hard-won gotchas, and a
"Current state & next steps" section that says exactly where the last session
left off. Read it before exploring the codebase; it usually makes exploration
unnecessary.

## What this repo is (10-second version)

Async FastAPI microservice that turns a script into a 9:16 captioned reel:
scenes → Hindi-first TTS (edge-tts → ElevenLabs fallback) → Pexels footage →
PIL word-by-word captions → FFmpeg/MoviePy MP4. Called by the separate **Keen**
Node backend — Keen = **NutriMama**, an AI lifelong-nutrition app for every
female across all life stages ("birth to death"), Hinglish-first, for Indian
users, with pregnancy as its strongest wedge (full context:
KNOWLEDGE_GRAPH.md §10) — via
`POST /api/v1/generate-video` + `X-Keen-Key`. Production =
Hugging Face Docker Space `KeenHunter/keen-video-service`, auto-deployed from
GitHub `main` by `.github/workflows/deploy-hf-space.yml`.

## Non-negotiable rules (details + reasons in KNOWLEDGE_GRAPH.md §6)

- MoviePy stays on **2.x** (`>=2.1,<3`); edge-tts stays **≥7.2** — the pins fix
  real breakage, don't "upgrade" or downgrade them casually.
- Caption text always comes from the **narration**, never from ElevenLabs'
  alignment (mangles Devanagari); font selection is **script-aware** — don't
  hardcode a single font path.
- Renders cost money (ElevenLabs on HF, since edge-tts is IP-blocked there) —
  keep the daily render cap and the `X-Keen-Key` auth intact.
- Render failures are soft by design (missing footage/BGM ⇒ degrade, don't
  fail); keep that property.
- `README.md`'s YAML frontmatter is the HF Space config — don't remove it.
- Pushing to `main` deploys to production. Work on branches + PRs.

## Run / verify

- Local: `.env` from `.env.example` (needs `PEXELS_API_KEY`), OS FFmpeg, then
  `uvicorn app.main:app --port 8000`. Smoke-test via `README.md` curl steps.
- Live: `GET /health` (has a `build` marker), key-gated `GET /api/v1/diag`
  (`?tts=1` costs ElevenLabs credits, `?caption=1` Devanagari self-test).

## Keep the memory fresh

After any significant change (feature, fix with a lesson, deploy change,
decision), **update `KNOWLEDGE_GRAPH.md` in the same commit** — at minimum its
§8 "Current state & next steps". That file only works if every session ends by
telling the next session where things stand.
