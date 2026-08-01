"""server.py — Flask app scaffolding for FuseMark

Routes live in app/routes/ (Flask Blueprints, grouped by concern) and are
registered at the bottom of this file. This module owns only what has to be
process-wide: the Flask app object itself, the DNS-rebinding/CSRF guard, the
413 handler, the recording-service singleton + its main.py-facing wrappers,
and small helpers shared across route groups.

Blueprint modules reach this module's state via `from app import server` +
`server.X` at call time (never `from app.server import X`) — tests rely on
monkeypatching attributes here (`_recording_service`, `_dl`, `_get_devices`,
`Recorder`, `_time`, ...) and late binding is what keeps that working after
the route split. See app/routes/__init__.py.
"""

import logging
import mimetypes
import os
import sys
import time as _time  # noqa: F401 — re-exported; patch target for app/routes/wizard.py tests
from urllib.parse import urlsplit

from flask import Flask, jsonify, request

# Not registered in the system mimetypes DB on all machines; self-hosted font
# asset needs the correct Content-Type regardless of host registry state.
mimetypes.add_type("font/woff2", ".woff2")

from app import queue as q
from app.recorder import Recorder  # noqa: F401 — re-exported; patch target for app/routes/wizard.py tests
from app.recording_service import RecordingService

logger = logging.getLogger(__name__)

_BASE = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(__file__))
app = Flask(
    __name__,
    template_folder=os.path.join(_BASE, "templates"),
    static_folder=os.path.join(_BASE, "static"),
)

# Cap request bodies (mainly audio uploads) to guard against disk-fill / OOM.
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB

# Largest transcript accepted via paste/import, in characters.
MAX_TRANSCRIPT_CHARS = 2_000_000


@app.errorhandler(413)
def _request_too_large(_err):
    return jsonify({"error": "Soubor je příliš velký (max 500 MB)."}), 413


# Loopback-only hostnames the app is ever legitimately reached on.
_ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


@app.before_request
def _validate_host_and_origin():
    """Reject requests whose Host isn't loopback (DNS rebinding) or whose
    Origin is a different site (CSRF). Origin is absent on same-origin
    requests from the app's own pywebview shell, so absence is allowed."""
    host = urlsplit(f"//{request.host}").hostname
    if host not in _ALLOWED_HOSTS:
        return jsonify({"error": "Forbidden"}), 403

    origin = request.headers.get("Origin")
    if origin and urlsplit(origin).hostname not in _ALLOWED_HOSTS:
        return jsonify({"error": "Forbidden"}), 403


_recording_service = RecordingService()


def set_tray(tray):
    _recording_service.set_tray(tray)


def set_on_recording(callback):
    _recording_service.on_recording = callback


# ------------------------------------------------------------------
# Recording control — thin wrappers so main.py needs no changes
# ------------------------------------------------------------------

def start_recording(label="", folder="", template=""):
    result = _recording_service.start(label=label, folder=folder, template=template)
    if "error" in result:
        return result, 400
    return result


def stop_recording():
    result = _recording_service.stop()
    if "error" in result:
        return result, 400
    return result


# ------------------------------------------------------------------
# Shared helpers — used by more than one route blueprint
# ------------------------------------------------------------------

_dl: dict = {}  # model_name -> {"downloading": bool, "downloaded_mb": float, "error": str|None}


def _recordings_size_mb(recordings_dir: str) -> float:
    if not os.path.isdir(recordings_dir):
        return 0.0
    total = sum(
        os.path.getsize(os.path.join(recordings_dir, f))
        for f in os.listdir(recordings_dir)
        if f.endswith(".mp3")
    )
    # In-progress and (until the next startup salvage) crash-orphaned partial
    # WAVs live under recordings/.partial/ — without this the Settings size
    # figure could silently miss GBs of them.
    partial_dir = os.path.join(recordings_dir, ".partial")
    if os.path.isdir(partial_dir):
        total += sum(
            os.path.getsize(os.path.join(partial_dir, f))
            for f in os.listdir(partial_dir)
            if os.path.isfile(os.path.join(partial_dir, f))
        )
    return total / (1024 * 1024)


def _dir_size_mb(path: str) -> float:
    """Return total size of a directory tree in MB."""
    if not os.path.isdir(path):
        return 0.0
    total = 0
    for dirpath, _, filenames in os.walk(path):
        for f in filenames:
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return total / (1024 * 1024)


def cleanup_recordings(data_dir, delete_processed=False, delete_orphans=True):
    from pathlib import Path
    recordings_dir = os.path.join(data_dir, "recordings")
    if not os.path.isdir(recordings_dir):
        return {"deleted": 0, "freed_mb": 0.0}
    all_jobs = q.list_jobs()
    known_paths = {j["audio_path"] for j in all_jobs if j.get("audio_path")}
    processed_paths = {
        j["audio_path"] for j in all_jobs
        if j.get("audio_path") and j["status"] in ("done", "error") and not j.get("keep_audio")
    }
    deleted, freed = 0, 0
    for mp3 in Path(recordings_dir).glob("*.mp3"):
        mp3_str = str(mp3)
        if delete_processed and mp3_str in processed_paths:
            freed += mp3.stat().st_size
            mp3.unlink(missing_ok=True)
            deleted += 1
        elif delete_orphans and mp3_str not in known_paths:
            freed += mp3.stat().st_size
            mp3.unlink(missing_ok=True)
            deleted += 1

    if delete_orphans:
        # Partial WAVs are named "<job_id>.system.wav" / "<job_id>.mic.wav".
        # Startup salvage (recording_service.salvage_interrupted_recordings)
        # is the primary recovery path — anything still here for a job that
        # isn't actively 'recording' is a leftover from a session that has
        # already been salvaged, failed to salvage, or no longer exists.
        partial_dir = Path(recordings_dir) / ".partial"
        if partial_dir.is_dir():
            active_ids = {j["id"] for j in all_jobs if j["status"] == "recording"}
            for wav in partial_dir.glob("*.wav"):
                session_id = wav.name.split(".")[0]
                if session_id not in active_ids:
                    freed += wav.stat().st_size
                    wav.unlink(missing_ok=True)
                    deleted += 1

    return {"deleted": deleted, "freed_mb": round(freed / (1024 * 1024), 1)}


def _get_devices():
    """Return list of device dicts for the settings page."""
    import pyaudiowpatch as pyaudio
    pa = pyaudio.PyAudio()
    devices = []
    try:
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            devices.append({
                "index": i,
                "name": d["name"],
                "is_input": d["maxInputChannels"] > 0,
                "is_output": d["maxOutputChannels"] > 0,
                "is_loopback": d.get("isLoopbackDevice", False),
            })
    finally:
        pa.terminate()
    return devices


def _get_vault_folders(vault_path):
    """Return existing subfolders under vault/FuseMark/Meetings/ for the dropdown."""
    if not vault_path:
        return ["Other"]
    meetings_dir = os.path.join(vault_path, "FuseMark", "Meetings")
    if not os.path.isdir(meetings_dir):
        return ["Other"]
    folders = [
        d for d in os.listdir(meetings_dir)
        if os.path.isdir(os.path.join(meetings_dir, d))
    ]
    return sorted(folders) or ["Other"]


def run(port=5000):
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)


from app.routes import register_blueprints  # noqa: E402 — must follow app + helpers above

register_blueprints(app)
