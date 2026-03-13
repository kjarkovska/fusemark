"""
server.py — Flask web server for Granola-CZ

Routes:
  GET  /              — main UI
  GET  /settings      — settings page
  POST /start         — start recording
  POST /stop          — stop recording
  GET  /jobs          — job list as JSON
  POST /jobs/<id>/context   — update extra_context on a job
  POST /jobs/<id>/audio     — set keep_audio decision
  GET  /status        — current recorder state as JSON
  POST /settings/save — save config
  POST /api-key       — store API key in keyring
"""

import json
import os
import threading
import webbrowser

from flask import Flask, jsonify, render_template, request

from app import config as cfg
from app import queue as q
from app.recorder import Recorder, list_devices as list_audio_devices

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
    static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
)

# Shared state — accessed from Flask routes and tray callbacks
_recorder = None
_recorder_lock = threading.Lock()
_current_job_id = None
_tray = None   # set by main.py after tray is created


def set_tray(tray):
    global _tray
    _tray = tray


# ------------------------------------------------------------------
# Recording control
# ------------------------------------------------------------------

def start_recording(label="", folder=""):
    global _recorder, _current_job_id
    with _recorder_lock:
        if _recorder is not None:
            return {"error": "Already recording"}, 400

        config = cfg.load()
        r = Recorder(
            output_device=config.get("output_device"),
            input_device=config.get("input_device"),
        )
        r.start()
        _recorder = r

        job_id = q.create_job(label=label, folder=folder)
        _current_job_id = job_id

    if _tray:
        _tray.set_recording(True)

    return {"job_id": job_id}


def stop_recording():
    global _recorder, _current_job_id
    with _recorder_lock:
        if _recorder is None:
            return {"error": "Not recording"}, 400

        r = _recorder
        job_id = _current_job_id
        _recorder = None
        _current_job_id = None

    r.stop()

    # Save the audio file and queue the job
    recordings_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "recordings"
    )
    os.makedirs(recordings_dir, exist_ok=True)
    audio_path = os.path.join(recordings_dir, f"{job_id}.mp3")
    r.save(audio_path)

    q.update_job(job_id, audio_path=audio_path, recording_path=audio_path)
    q.set_status(job_id, "queued")

    if _tray:
        _tray.set_recording(False)

    return {"job_id": job_id, "audio_path": audio_path}


# ------------------------------------------------------------------
# Flask routes
# ------------------------------------------------------------------

@app.route("/")
def index():
    config = cfg.load()
    folders = _get_vault_folders(config.get("vault_path", ""))
    return render_template("index.html", config=config, folders=folders)


@app.route("/settings")
def settings():
    config = cfg.load()
    devices = _get_devices()
    return render_template("settings.html", config=config, devices=devices)


@app.route("/start", methods=["POST"])
def route_start():
    data = request.get_json(silent=True) or {}
    result = start_recording(
        label=data.get("label", ""),
        folder=data.get("folder", "Other"),
    )
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result)


@app.route("/stop", methods=["POST"])
def route_stop():
    data = request.get_json(silent=True) or {}
    # Save scratch notes if provided before stopping
    if _current_job_id and data.get("scratch_notes"):
        q.update_job(_current_job_id, scratch_notes=data["scratch_notes"])
    result = stop_recording()
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result)


@app.route("/jobs")
def route_jobs():
    jobs = q.list_jobs()
    return jsonify(jobs)


@app.route("/jobs/<job_id>/context", methods=["POST"])
def route_job_context(job_id):
    data = request.get_json(silent=True) or {}
    q.update_job(job_id, extra_context=data.get("context", ""))
    return jsonify({"ok": True})


@app.route("/jobs/<job_id>/audio", methods=["POST"])
def route_job_audio(job_id):
    data = request.get_json(silent=True) or {}
    keep = 1 if data.get("keep") else 0
    q.update_job(job_id, keep_audio=keep)

    if not keep:
        job = q.get_job(job_id)
        audio = job.get("audio_path") or job.get("recording_path")
        if audio and os.path.exists(audio):
            os.remove(audio)

    return jsonify({"ok": True})


@app.route("/status")
def route_status():
    with _recorder_lock:
        recording = _recorder is not None
        job_id = _current_job_id
    return jsonify({"recording": recording, "job_id": job_id})


@app.route("/settings/save", methods=["POST"])
def route_settings_save():
    data = request.get_json(silent=True) or {}
    config = cfg.load()
    for key in ("vault_path", "whisper_model"):
        if key in data:
            config[key] = data[key]
    for key in ("output_device", "input_device"):
        val = data.get(key)
        config[key] = int(val) if val not in (None, "", "null") else None
    cfg.save(config)
    return jsonify({"ok": True})


@app.route("/open-glossary", methods=["POST"])
def route_open_glossary():
    from app.glossary import open_in_vscode
    open_in_vscode()
    return jsonify({"ok": True})


@app.route("/api-key", methods=["POST"])
def route_api_key():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    if not key:
        return jsonify({"error": "No key provided"}), 400
    from app.notemaker import set_api_key
    set_api_key(key)
    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

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
    """Return existing subfolders under vault/Meetings/ for the dropdown."""
    if not vault_path:
        return ["Other"]
    meetings_dir = os.path.join(vault_path, "Meetings")
    if not os.path.isdir(meetings_dir):
        return ["Other"]
    folders = [
        d for d in os.listdir(meetings_dir)
        if os.path.isdir(os.path.join(meetings_dir, d))
    ]
    return sorted(folders) or ["Other"]


def open_browser(port=5000):
    webbrowser.open(f"http://127.0.0.1:{port}")


def run(port=5000, open_on_start=True):
    if open_on_start:
        threading.Timer(0.8, open_browser, args=[port]).start()
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
