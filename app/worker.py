"""
worker.py — Background job processor for Granola-CZ

Runs in a daemon thread. Polls the job queue for jobs in 'queued' state,
processes them one at a time through the pipeline:

  queued -> transcribing -> (transcriber.py) -> generating -> (notemaker.py) -> done

Errors are caught per-job: the job is marked 'error' and the worker
moves on to the next job without crashing.
"""

import threading
import time

from app import queue as q
from app import config as cfg
from app.transcriber import transcribe


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
        """Phase 4 will replace this stub with Claude API call."""
        q.set_status(job_id, "generating")
        # stub — implemented in Phase 4
