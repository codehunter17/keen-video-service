# Deploy the Keen Video Service to a Hugging Face Space (free, no card)

Hugging Face **Docker Spaces** run any `Dockerfile` on a free CPU instance
(2 vCPU / 16 GB RAM) — no credit card, ever. This service is already a Docker
HTTP app, so it runs here unchanged except for HF's port + non-root-user rules,
which are already baked into the `Dockerfile` and `README.md`.

Why HF instead of Cloud Run: Cloud Run requires a billing account (card). HF
doesn't. Bonus: HF runs the container continuously, so — unlike Cloud Run — we
don't need the `--no-cpu-throttling` workaround for the async background render.

Account used below: **`KeenHunter`**. Space name: **`keen-video-service`**.
Public app URL it will get: `https://keenhunter-keen-video-service.hf.space`

---

## 1. Create the Space (web, ~30s)
1. Go to <https://huggingface.co/new-space>.
2. **Owner:** KeenHunter · **Space name:** `keen-video-service`
3. **SDK:** Docker → **Blank** template.
4. **Visibility:** Public *(the render endpoint is gated by our own
   `SERVICE_API_KEY`, so public is fine and means Keen needs no extra auth).*
5. Create. Leave the empty Space — we push our code into it next.

## 2. Add the secrets (Space → Settings → "Variables and secrets")
Add these as **Secrets** (not Variables):

| Key | Value | Notes |
|---|---|---|
| `PEXELS_API_KEY` | your Pexels key | **Required** — free at <https://www.pexels.com/api/>. Without it there's no footage to fetch. |
| `SERVICE_API_KEY` | a random string | The shared secret. Generate one (e.g. `openssl rand -hex 24`). The **same** value goes to Vercel in step 5. |
| `PUBLIC_BASE_URL` | `https://keenhunter-keen-video-service.hf.space` | So `output_url` links to the MP4s resolve. |
| `GROQ_API_KEY` *(optional)* | your Groq key | Richer scene prompts; falls back to a keyword heuristic if absent. |
| `GEMINI_API_KEY` *(optional)* | your Gemini key | Alternative to Groq for scene prompts. |

Leave `TTS_PROVIDER` unset — it defaults to `edge` (free neural TTS), so you need
no ElevenLabs key.

## 3. Push this repo to the Space
From inside `keen-video-service/`. You'll need an HF **write** token
(<https://huggingface.co/settings/tokens>). When `git push` asks for a password,
paste the token (username can be `KeenHunter`).

```bash
cd keen-video-service

# commit the HF-ready Dockerfile + README frontmatter
git add Dockerfile README.md DEPLOY_HF_SPACE.md
git commit -m "Add Hugging Face Space deploy (Docker SDK)"

# add the Space as a second remote and push
git remote add space https://huggingface.co/spaces/KeenHunter/keen-video-service
# --force is needed ONCE: a new Space ships with an auto-generated commit
# (HF's README + .gitattributes) that our repo's history doesn't share, so a
# plain push is rejected. Force overwrites that boilerplate — safe on a fresh Space.
git push space main --force
```

The Space auto-builds on push. Watch **Logs / Building** in the Space UI; first
build takes a few minutes (FFmpeg + wheels). It flips to **Running** when ready.

## 4. Verify
Open <https://keenhunter-keen-video-service.hf.space/health> — you want:
```json
{ "ok": true, "tts_provider": "edge", "pexels_configured": true, "video_size": [1080, 1920] }
```
`pexels_configured: true` confirms the secret landed. If it's `false`, re-check step 2.

## 5. Point Keen at it (Vercel → your NutriMama project → Settings → Env Vars, Production)
| Key | Value |
|---|---|
| `VIDEO_SERVICE_URL` | `https://keenhunter-keen-video-service.hf.space` |
| `VIDEO_SERVICE_KEY` | the **same** `SERVICE_API_KEY` from step 2 |

Redeploy `my-app`. Keen's `request_video` / `check_video_status` tools go live
(they read these two vars via `my-app/lib/video-service.ts`).

---

## Free-tier caveats (fine for v1)
- **Sleeps after ~48h idle** and cold-starts on the next request. The first call
  after a sleep can take longer than Keen's 15s enqueue timeout — if so, just
  retry, or hit `/health` once to warm it before asking Keen for a reel.
- **Ephemeral disk:** rendered MP4s are wiped on restart. Keen polls `/status`
  and gets the URL right after render, so this is fine short-term. For durable
  links later, attach an HF Storage Bucket or push outputs to a bucket/S3.
- **One render at a time** (`--workers 1`, CPU-bound). Plenty for current volume;
  add a queue + more instances when reels demand grows.
