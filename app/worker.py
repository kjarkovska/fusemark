"""
worker.py — Background job processor for Granola-CZ

Runs in a daemon thread. Polls the job queue for jobs in 'queued' state,
processes them one at a time through the pipeline:

  queued -> transcribing -> (transcriber.py) -> generating -> (notemaker.py) -> done

Errors are caught per-job: the job is marked 'error' and the worker
moves on to the next job without crashing.
"""

import json
import threading
import time

from app import queue as q
from app import config as cfg
from app.transcriber import transcribe
from app.notemaker import generate_notes, suggest_glossary_terms, save_note


POLL_INTERVAL = 5  # seconds between queue checks


class Worker:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        """Start the background worker thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="worker")
        self._thread.start()
        print("[worker] Started")

    def stop(self):
        """Signal the worker to stop and wait for it to finish."""
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
        """Pick the oldest queued job and process it."""
        jobs = q.list_jobs(status="queued")
        if not jobs:
            return

        # Oldest first
        job = sorted(jobs, key=lambda j: j["created_at"])[0]
        job_id = job["id"]
        print(f"[worker] Processing job {job_id} — '{job.get('label', '')}'")

        try:
            self._transcribe(job_id, job)
            job = q.get_job(job_id)  # re-fetch to pick up transcript written by transcriber
            self._generate(job_id, job)
            q.set_status(job_id, "done")
            print(f"[worker] Job {job_id} done")
        except Exception as exc:
            q.update_job(job_id, status="error", error_message=str(exc))
            print(f"[worker] Job {job_id} error: {exc}")

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
            raise ValueError("vault_path not set in config.json.")

        transcript = job.get("transcript", "")
        note = generate_notes(
            transcript=transcript,
            label=job.get("label", ""),
            folder=job.get("folder", "Other"),
            scratch_notes=job.get("scratch_notes", "") or "",
            extra_context=job.get("extra_context", "") or "",
        )
        out_path = save_note(note, job.get("label", ""), job.get("folder", "Other"), vault_path)
        q.update_job(job_id, output_note_path=out_path)

        terms = suggest_glossary_terms(transcript)
        if terms:
            # Store suggestions in the job for the UI to present to the user
            q.update_job(job_id, error_message=json.dumps(terms, ensure_ascii=False))
