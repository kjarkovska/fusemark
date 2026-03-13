"""
worker.py — Background job processor for Granola-CZ

  queued -> transcribing -> generating -> done

Error strategy:
  - Transcription error  → job marked 'error', audio preserved (needs human review)
  - Claude API error     → job reset to 'queued' for automatic retry (up to MAX_RETRIES)
  - vault_path not set   → job reset to 'queued', retries once vault is configured
"""

import json
import threading
import time

import anthropic

from app import queue as q
from app import config as cfg
from app.transcriber import transcribe
from app.notemaker import generate_notes, suggest_glossary_terms, save_note


POLL_INTERVAL = 5   # seconds between queue checks
MAX_RETRIES = 5     # max retries for generation errors before marking as error


class Worker:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="worker")
        self._thread.start()
        print("[worker] Started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        print("[worker] Stopped")

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self._process_next()
            except Exception as exc:
                print(f"[worker] Unexpected error in loop: {exc}")
            self._stop_event.wait(POLL_INTERVAL)

    def _process_next(self):
        jobs = q.list_jobs(status="queued")
        if not jobs:
            return

        job = sorted(jobs, key=lambda j: j["created_at"])[0]
        job_id = job["id"]
        print(f"[worker] Processing job {job_id} — '{job.get('label', '')}'")

        # Transcription errors → error state (audio preserved, needs human action)
        try:
            self._transcribe(job_id, job)
        except Exception as exc:
            q.update_job(job_id, status="error", error_message=f"Transcription failed: {exc}")
            print(f"[worker] Job {job_id} transcription error: {exc}")
            return

        job = q.get_job(job_id)  # re-fetch to pick up transcript

        # Generation errors → retry up to MAX_RETRIES, then error
        try:
            self._generate(job_id, job)
        except _RetryableError as exc:
            retries = _parse_retry_count(job.get("error_message", ""))
            if retries < MAX_RETRIES:
                q.update_job(
                    job_id,
                    status="queued",
                    error_message=f"retry:{retries + 1}:{exc}",
                )
                print(f"[worker] Job {job_id} will retry ({retries + 1}/{MAX_RETRIES}): {exc}")
            else:
                q.update_job(job_id, status="error", error_message=f"Generation failed after {MAX_RETRIES} retries: {exc}")
                print(f"[worker] Job {job_id} exceeded max retries: {exc}")
            return
        except Exception as exc:
            q.update_job(job_id, status="error", error_message=f"Generation failed: {exc}")
            print(f"[worker] Job {job_id} generation error: {exc}")
            return

        q.set_status(job_id, "done")
        print(f"[worker] Job {job_id} done")

    def _transcribe(self, job_id, job):
        q.set_status(job_id, "transcribing")
        audio_path = job.get("audio_path") or job.get("recording_path")
        if not audio_path:
            raise ValueError("Job has no audio_path to transcribe.")
        config = cfg.load()
        model_size = config.get("whisper_model", "large-v3")
        transcript = transcribe(audio_path, model_size=model_size, job_id=job_id)
        q.update_job(job_id, transcript=transcript)

    def _generate(self, job_id, job):
        q.set_status(job_id, "generating")
        config = cfg.load()
        vault_path = config.get("vault_path", "")
        if not vault_path:
            raise _RetryableError("vault_path not set — configure it in Settings")

        transcript = job.get("transcript") or ""
        try:
            note = generate_notes(
                transcript=transcript,
                label=job.get("label", ""),
                folder=job.get("folder", "Other"),
                scratch_notes=job.get("scratch_notes", "") or "",
                extra_context=job.get("extra_context", "") or "",
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError) as exc:
            raise _RetryableError(str(exc)) from exc

        out_path = save_note(note, job.get("label", ""), job.get("folder", "Other"), vault_path)
        q.update_job(job_id, output_note_path=out_path)

        try:
            terms = suggest_glossary_terms(transcript)
            if terms:
                q.update_job(job_id, error_message=json.dumps(terms, ensure_ascii=False))
        except Exception as exc:
            print(f"[worker] Glossary suggestion failed (non-fatal): {exc}")


class _RetryableError(Exception):
    """Raised when a generation step fails but should be retried automatically."""


def _parse_retry_count(error_message):
    """Extract retry count from error_message field (format: 'retry:N:...')."""
    if error_message and error_message.startswith("retry:"):
        try:
            return int(error_message.split(":")[1])
        except (IndexError, ValueError):
            pass
    return 0
