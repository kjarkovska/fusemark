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

            config = cfg.load()
            r = Recorder(
                output_device=config.get("output_device"),
                input_device=config.get("input_device"),
            )
            try:
                r.start()
            except Exception as exc:
                logger.error("Failed to start recording: %s", exc)
                return {"error": str(exc)}
            self._recorder = r

            job_id = q.create_job(label=label, folder=folder)
            if template:
                q.update_job(job_id, template=template)
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
            q.update_job(job_id, status="error", error_message=f"Recording could not be saved: {exc}")
            self._notify_stopped()
            return {"error": str(exc)}

        q.update_job(job_id, audio_path=audio_path, recording_path=audio_path)
        q.set_status(job_id, "queued")
        self._notify_stopped()

        logger.info("Recording stopped, job %s queued", job_id)
        return {"job_id": job_id, "audio_path": audio_path}
