"""
worker.py — Background job processor for ObsiNote

  queued -> transcribing -> generating -> done

Error strategy:
  - Transcription error  → job marked 'error', audio preserved (needs human review)
  - Claude API error     → job reset to 'queued' for automatic retry (up to MAX_RETRIES)
  - vault_path not set   → job reset to 'queued', retries once vault is configured
"""

import json
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

from app import queue as q
from app import config as cfg
from app.exceptions import ModelNotReadyError, LLMRateLimitError, LLMAuthError
from app.transcription import transcribe
from app.llm import generate_notes, suggest_glossary_terms
from app.notes import save_note, save_transcript


POLL_INTERVAL = 5   # seconds between queue checks
MAX_RETRIES = 5     # max retries for generation errors before marking as error


class Worker:
    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self.on_transcribing = None  # optional callback(bool) — wired to tray in main.py
        self.on_tooltip = None       # optional callback(str) — wired to tray.set_tooltip in main.py

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="worker")
        self._thread.start()
        logger.info("Started")

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Stopped")

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                self._process_next()
            except Exception as exc:
                logger.error("Unexpected error in loop: %s", exc)
            self._stop_event.wait(POLL_INTERVAL)

    def _process_next(self):
        jobs = q.list_jobs(status="queued")
        if not jobs:
            return

        job = sorted(jobs, key=lambda j: j["created_at"])[0]
        job_id = job["id"]
        logger.info("Processing job %s — '%s'", job_id, job.get('label', ''))

        if not job.get("transcript"):
            # Normal flow — transcribe from audio
            try:
                self._transcribe(job_id, job)
            except ModelNotReadyError as exc:
                q.update_job(job_id, status="error", error_message=str(exc))
                logger.error("Job %s model not ready: %s", job_id, exc)
                if self.on_tooltip:
                    self.on_tooltip("ObsiNote")
                return
            except Exception as exc:
                q.update_job(job_id, status="error", error_message=f"Transcription failed: {exc}")
                logger.error("Job %s transcription error: %s", job_id, exc)
                if self.on_tooltip:
                    self.on_tooltip("ObsiNote")
                return
            job = q.get_job(job_id)  # re-fetch to pick up transcript
        # else: transcript pre-populated (imported) — skip directly to generation

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
                logger.warning("Job %s will retry (%s/%s): %s", job_id, retries + 1, MAX_RETRIES, exc)
            else:
                q.update_job(job_id, status="error", error_message=f"Generation failed after {MAX_RETRIES} retries: {exc}")
                logger.error("Job %s exceeded max retries: %s", job_id, exc)
            if self.on_tooltip:
                self.on_tooltip("ObsiNote")
            return
        except Exception as exc:
            q.update_job(job_id, status="error", error_message=f"Generation failed: {exc}")
            logger.error("Job %s generation error: %s", job_id, exc)
            if self.on_tooltip:
                self.on_tooltip("ObsiNote")
            return

        q.set_status(job_id, "done")
        self._maybe_delete_recording(job_id)
        logger.info("Job %s done", job_id)
        if self.on_tooltip:
            self.on_tooltip("ObsiNote")

    def _transcribe(self, job_id, job):
        label = job.get("label") or "Porada"
        q.set_status(job_id, "transcribing")
        if self.on_transcribing:
            self.on_transcribing(True)
        if self.on_tooltip:
            self.on_tooltip(f"ObsiNote — Přepisuji: {label}")
        try:
            audio_path = job.get("audio_path") or job.get("recording_path")
            if not audio_path:
                raise ValueError("Job has no audio_path to transcribe.")
            transcript = transcribe(audio_path, job_id=job_id)
            q.update_job(job_id, transcript=transcript)
        finally:
            if self.on_transcribing:
                self.on_transcribing(False)

    def _generate(self, job_id, job):
        label = job.get("label") or "Porada"
        q.set_status(job_id, "generating")
        if self.on_tooltip:
            self.on_tooltip(f"ObsiNote — Generuji poznámky: {label}")
        config = cfg.load()
        vault_path = config.get("vault_path", "")
        if not vault_path:
            raise _RetryableError("vault_path not set — configure it in Settings")

        transcript = job.get("transcript") or ""
        date_str = job.get("meeting_date", "") or ""

        transcript_path = save_transcript(transcript, job.get("label", ""), vault_path, date_str=date_str)
        if transcript_path:
            q.update_job(job_id, transcript_path=transcript_path)

        try:
            note = generate_notes(
                transcript=transcript,
                label=job.get("label", ""),
                folder=job.get("folder", "Other"),
                scratch_notes=job.get("scratch_notes", "") or "",
                extra_context=job.get("extra_context", "") or "",
                language=config.get("language_name", "Czech"),
            )
        except LLMRateLimitError as exc:
            raise _RetryableError(str(exc)) from exc

        out_path = save_note(note, job.get("label", ""), job.get("folder", "Other"), vault_path, date_str=date_str)
        q.update_job(job_id, output_note_path=out_path)

        try:
            terms = suggest_glossary_terms(transcript)
            if terms:
                q.update_job(job_id, glossary_terms=json.dumps(terms, ensure_ascii=False))
        except Exception as exc:
            logger.debug("Glossary suggestion failed (non-fatal): %s", exc)


    def _maybe_delete_recording(self, job_id):
        config = cfg.load()
        if config.get("auto_delete_recordings"):
            job = q.get_job(job_id)
            if job.get("keep_audio") != 1:
                audio = job.get("audio_path") or job.get("recording_path")
                if audio and os.path.exists(audio):
                    try:
                        os.remove(audio)
                        q.update_job(job_id, audio_path=None)
                        logger.info("Auto-deleted recording for job %s", job_id)
                    except OSError as exc:
                        logger.warning("Could not delete recording %s: %s", audio, exc)
        elif config.get("max_recordings_gb", 0) > 0:
            _enforce_size_limit(config)


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


def _enforce_size_limit(config):
    from pathlib import Path
    from app.config import DATA_DIR
    limit_bytes = config["max_recordings_gb"] * 1024 ** 3
    recordings_dir = os.path.join(DATA_DIR, "recordings")
    candidates = sorted(
        [j for j in q.list_jobs(status="done") if j.get("audio_path") and j.get("keep_audio") != 1],
        key=lambda j: j["created_at"],
    )
    for job in candidates:
        total = sum(f.stat().st_size for f in Path(recordings_dir).glob("*.mp3") if f.exists())
        if total <= limit_bytes:
            break
        audio = job["audio_path"]
        if os.path.exists(audio):
            try:
                os.remove(audio)
                q.update_job(job["id"], audio_path=None)
                logger.info("Size-limit cleanup: deleted %s", audio)
            except OSError as exc:
                logger.warning("Could not delete %s: %s", audio, exc)
