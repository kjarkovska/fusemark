"""Recording lifecycle: start/stop/status and recordings housekeeping."""

import os

from flask import Blueprint, jsonify, request

from app import config as cfg
from app import queue as q
from app import server

bp = Blueprint("recording", __name__)


@bp.route("/start", methods=["POST"])
def route_start():
    data = request.get_json(silent=True) or {}
    result = server.start_recording(
        label=data.get("label", ""),
        folder=data.get("folder", "Other"),
        template=data.get("template", ""),
    )
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result)


@bp.route("/stop", methods=["POST"])
def route_stop():
    data = request.get_json(silent=True) or {}
    # Save scratch notes if provided before stopping
    current_job_id = server._recording_service.current_job_id
    if current_job_id and data.get("scratch_notes"):
        q.update_job(current_job_id, scratch_notes=data["scratch_notes"])
    result = server.stop_recording()
    if isinstance(result, tuple):
        return jsonify(result[0]), result[1]
    return jsonify(result)


@bp.route("/status")
def route_status():
    return jsonify({
        "recording": server._recording_service.is_recording,
        "job_id": server._recording_service.current_job_id,
    })


@bp.route("/level")
def route_level():
    """Real capture signal, polled by the frontend level meter while
    recording. Always 200 — the browser polls this on a race with
    start/stop, and a transient 4xx would just be noise in that window."""
    recorder = server._recording_service.recorder
    if recorder is None:
        return jsonify({
            "recording": False,
            "system": 0.0,
            "mic": 0.0,
            "signal": False,
            "system_silent": False,
            "mic_silent": False,
        })
    levels = recorder.levels()
    return jsonify({
        "recording": True,
        "system": levels["system"],
        "mic": levels["mic"],
        "signal": bool(levels["system_bytes"] or levels["mic_bytes"]),
        "system_silent": levels["system_silent"],
        "mic_silent": levels["mic_silent"],
    })


@bp.route("/recordings/size")
def recordings_size():
    d = os.path.join(cfg.DATA_DIR, "recordings")
    mb = round(server._recordings_size_mb(d), 1)
    return jsonify({"size_mb": mb, "size_gb": round(mb / 1024, 2)})


@bp.route("/recordings/cleanup", methods=["POST"])
def recordings_cleanup():
    result = server.cleanup_recordings(cfg.DATA_DIR, delete_processed=True, delete_orphans=True)
    return jsonify(result)
