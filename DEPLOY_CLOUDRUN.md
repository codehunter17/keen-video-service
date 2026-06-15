# Deploy the Keen Video Service to Google Cloud Run

Cloud Run is serverless (scales to zero ≈ free at low volume), supports long
FFmpeg renders, and runs the included `Dockerfile` directly. One-time setup,
then a single deploy command.

## 0. One-time prerequisites
1. Install the **gcloud CLI**: https://cloud.google.com/sdk/docs/install (Windows installer).
2. Log in (opens a browser):
   ```bash
   gcloud auth login
   ```
3. Create (or pick) a project and select it:
   ```bash
   gcloud projects create keen-video-123 --name="Keen Video"   # pick a globally-unique id
   gcloud config set project keen-video-123
   ```
4. **Enable billing** on that project in the console (Cloud Run requires a billing
   account even though the free tier covers low usage):
   https://console.cloud.google.com/billing
5. Enable the APIs the deploy needs:
   ```bash
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
   ```

## 1. Deploy (builds the Dockerfile + ships it)
Fill in your real keys, then run from inside `keen-video-service/`:
```bash
gcloud run deploy keen-video-service \
  --source . \
  --region asia-south1 \
  --memory 2Gi \
  --cpu 2 \
  --timeout 900 \
  --concurrency 1 \
  --min-instances 0 \
  --no-cpu-throttling \
  --allow-unauthenticated \
  --set-env-vars "PEXELS_API_KEY=YOUR_PEXELS_KEY,SERVICE_API_KEY=YOUR_RANDOM_SECRET,VIDEO_WIDTH=1080,VIDEO_HEIGHT=1920,PUBLIC_BASE_URL=https://PLACEHOLDER"
```
- `--concurrency 1`: rendering is CPU-bound — one job per instance.
- `--min-instances 0`: scale to zero, so you pay nothing while idle.
- `--no-cpu-throttling`: **required** — the render runs as a background task
  *after* the API returns the job_id; without this, Cloud Run throttles CPU
  post-response and the render would stall. Still scales to zero when truly idle.
- `--allow-unauthenticated`: fine — our own `SERVICE_API_KEY` (`X-Keen-Key`) gates it.

It prints a **Service URL** like `https://keen-video-service-xxxxx.a.run.app`.

## 2. Finish config
1. Re-deploy once with `PUBLIC_BASE_URL` set to that real URL (so `output_url`
   links resolve), or update it later:
   ```bash
   gcloud run services update keen-video-service --region asia-south1 \
     --set-env-vars "PUBLIC_BASE_URL=https://keen-video-service-xxxxx.a.run.app"
   ```
2. Verify: open `https://keen-video-service-xxxxx.a.run.app/health` → `{"ok": true, ...}`.

## 3. Point Keen at it (Vercel)
In Vercel → nutrimama-v3 → Settings → Environment Variables (Production):
- `VIDEO_SERVICE_URL` = the Cloud Run URL
- `VIDEO_SERVICE_KEY` = the same `SERVICE_API_KEY`

Then redeploy `my-app` and Keen's `request_video` / `check_video_status` tools go live.

## Notes
- Region `asia-south1` = Mumbai (low latency for India). Change if you prefer.
- Rendered MP4s are served from the instance (`/files/...`). For durable storage
  (so links survive scale-to-zero), add a GCS bucket later — fine to skip for v1.
