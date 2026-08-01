"""
recording_service.py — Recording lifecycle for FuseMark

Owns the recorder instance and current-job state that previously lived as
module-level globals in server.py.  Flask routes delegate here; main.py
calls start_recording() / stop_recording() via server.py wrappers, which
also delegate here — so nothing outside this class touches the recorder.
"""

import logging
import os
import threading
from typing import TYPE_CHECKING

from app import config as cfg
from app import queue as q

if TYPE_CHECKING:  # avoid importing pyaudiowpatch at module load; Recorder is lazily imported in start()
    from app.recorder import Recorder

logger = logging.getLogger(__name__)


class RecordingService:
    def __init__(self, tray=None):
        self._recorder: Recorder | None = None
        self._current_job_id: str | None = None
        self._lock = threading.Lock()
        self._tray = tray
        self.on_recording = None  # optional callback(bool) — wired to taskbar update in main.py

    def set_tray(self, tray) -> None:
        self._tray = tray

    @property
    def tray(self):
        return self._tray

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recorder is not None

    @property
    def current_job_id(self) -> str | None:
        with self._lock:
            return self._current_job_id

    def start(self, label: str = "", folder: str = "", template: str = "") -> dict:
        from app.recorder import Recorder
        with self._lock:
            if self._recorder is not None:
                return {"error": "Already recording"}

            # Job must exist before the recorder starts capturing, so its id
            # can name the partial WAV files on disk — that's what lets a
            # crash mid-recording be matched back to this job at the next
            # startup (see salvage_interrupted_recordings below).
            job_id = q.create_job(label=label, folder=folder)
            if template:
                q.update_job(job_id, template=template)

            config = cfg.load()
            r = Recorder(
                output_device=config.get("output_device"),
                input_device=config.get("input_device"),
                session_id=job_id,
            )
            try:
                r.start()
            except Exception as exc:
                logger.error("Failed to start recording: %s", exc)
                q.update_job(job_id, status="error",
                             error_message=f"Recording could not be started: {exc}")
                return {"error": str(exc)}
            self._recorder = r
            self._current_job_id = job_id

        if self._tray:
            self._tray.set_recording(True)
            self._tray.set_tooltip("FuseMark — Nahrávám")
        if self.on_recording:
            self.on_recording(True)

        logger.info("Recording started, job %s", job_id)
        return {"job_id": job_id}

    def _notify_stopped(self):
        if self._tray:
            self._tray.set_recording(False)
            self._tray.set_tooltip("FuseMark")
        if self.on_recording:
            self.on_recording(False)

    def stop(self) -> dict:
        with self._lock:
            if self._recorder is None:
                return {"error": "Not recording"}

            r = self._recorder
            job_id = self._current_job_id
            self._recorder = None
            self._current_job_id = None

        try:
            r.stop()
            recordings_dir = os.path.join(cfg.DATA_DIR, "recordings")
            os.makedirs(recordings_dir, exist_ok=True)
            audio_path = os.path.join(recordings_dir, f"{job_id}.mp3")
            r.save(audio_path)
        except Exception as exc:
            logger.error("Failed to save recording for job %s: %s", job_id, exc)
            try:
                # r.save()'s own cleanup only runs if save() itself was
                # reached — if r.stop() is what raised, the partial WAVs are
                # still on disk. discard() is idempotent, so calling it here
                # is always safe even when save() already cleaned up.
                r.discard()
            except Exception:
                logger.exception("Failed to clean up recorder temp files for job %s", job_id)
            q.update_job(job_id, status="error", error_message=f"Recording could not be saved: {exc}")
            self._notify_stopped()
            return {"error": str(exc)}

        q.update_job(job_id, audio_path=audio_path, recording_path=audio_path)
        q.set_status(job_id, "queued")
        self._notify_stopped()

        logger.info("Recording stopped, job %s queued", job_id)
        return {"job_id": job_id, "audio_path": audio_path}


def salvage_interrupted_recordings() -> int:
    """Recover recordings left mid-capture by a crash: a job stuck in
    'recording' state whose partial WAVs are still on disk under
    recordings/.partial/. Call once at startup, before
    queue.recover_interrupted_jobs() marks any still-stuck 'recording' job as
    an error — a session salvaged here is queued for processing instead.

    Also sweeps orphan partial files (no matching job, or the job moved on
    to a different status) so .partial/ doesn't accumulate disk usage forever.

    Returns the number of jobs salvaged.
    """
    from app.recorder import list_partial_sessions, partial_paths, salvage_partial

    salvaged = 0
    for session_id in list_partial_sessions():
        job = q.get_job(session_id)

        if job is None or job["status"] != "recording":
            for path in partial_paths(session_id):
                if os.path.exists(path):
                    try:
                        os.unlink(path)
                    except OSError:
                        logger.warning("Failed to remove orphan partial WAV: %s", path)
            continue

        recordings_dir = os.path.join(cfg.DATA_DIR, "recordings")
        os.makedirs(recordings_dir, exist_ok=True)
        audio_path = os.path.join(recordings_dir, f"{session_id}.mp3")

        result = salvage_partial(session_id, audio_path)
        if result:
            q.update_job(session_id, audio_path=audio_path, recording_path=audio_path)
            q.set_status(session_id, "queued")
            salvaged += 1
            logger.info("Salvaged interrupted recording for job %s", session_id)
        else:
            logger.warning("Could not salvage interrupted recording for job %s", session_id)

    if salvaged:
        logger.info("Salvaged %d interrupted recording(s)", salvaged)
    return salvaged
