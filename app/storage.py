"""Optional durable storage for finished renders.

The HF Space disk is ephemeral: MP4s under output/ vanish on every Space
restart, which kills previously shared /files/ links (WhatsApp, demos). When
HF_OUTPUT_REPO (+ a write-capable HF_TOKEN) is configured, each finished MP4
is also uploaded to a Hugging Face *dataset* repo and the job's output_url
points at the durable resolve URL instead.

Soft-fail by design (same property as footage/BGM): a missing config or a
failed upload never fails the render — the caller keeps the local /files/ URL.
"""

from __future__ import annotations

import logging

from .config import get_settings

log = logging.getLogger("storage")

_repo_ready = False


def durable_storage_configured() -> bool:
    s = get_settings()
    return bool(s.hf_output_repo and s.hf_token)


def upload_output(local_path: str, job_id: str) -> str | None:
    """Upload a finished MP4 to the configured HF dataset repo.

    Returns the public resolve URL, or None when unconfigured or on any
    failure (callers fall back to the ephemeral /files/ URL).
    """
    s = get_settings()
    if not durable_storage_configured():
        log.debug("durable storage not configured (HF_OUTPUT_REPO/HF_TOKEN); keeping local URL")
        return None
    try:
        # Imported lazily so the service (and tests) run without the package
        # in environments where durable storage is never used.
        from huggingface_hub import HfApi

        global _repo_ready
        api = HfApi(token=s.hf_token)
        if not _repo_ready:
            # Public repo: the whole point is links that outlive the Space and
            # open for anyone (WhatsApp shares). exist_ok makes this idempotent.
            api.create_repo(s.hf_output_repo, repo_type="dataset", exist_ok=True)
            _repo_ready = True
        path_in_repo = f"videos/{job_id}.mp4"
        api.upload_file(
            path_or_fileobj=local_path,
            path_in_repo=path_in_repo,
            repo_id=s.hf_output_repo,
            repo_type="dataset",
        )
        url = f"https://huggingface.co/datasets/{s.hf_output_repo}/resolve/main/{path_in_repo}"
        log.info("uploaded %s → %s", local_path, url)
        return url
    except Exception as e:  # noqa: BLE001 — durable storage must never fail a render
        log.warning("durable upload failed (%s); keeping local /files/ URL", e)
        return None
