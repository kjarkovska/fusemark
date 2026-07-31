"""Job import (transcript/audio) and job list CRUD/actions."""

import os

from flask import Blueprint, jsonify, request

from app import config as cfg
from app import queue as q
from app import server

bp = Blueprint("jobs", __name__)


@bp.route("/import-transcript", methods=["POST"])
def route_import_transcript():
    data = request.get_json(silent=True) or {}
    transcript = (data.get("transcript") or "").strip()
    if not transcript:
        return jsonify({"error": "transcript required"}), 400
    if len(transcript) > server.MAX_TRANSCRIPT_CHARS:
        return jsonify({"error": "transcript too large"}), 413

    job_id = q.create_job(
        label=data.get("label", ""),
        folder=data.get("folder", "Other"),
    )
    q.update_job(
        job_id,
        transcript=transcript,
        template=data.get("template", "") or None,
        meeting_date=data.get("meeting_date", "") or None,
    )
    q.set_status(job_id, "queued")

    tray = server._recording_service.tray
    if tray:
        tray.set_tooltip("FuseMark — Zpracovávám import")

    return jsonify({"job_id": job_id})


@bp.route("/import-audio", methods=["POST"])
def route_import_audio():
    if "audio" not in request.files:
        return jsonify({"error": "audio file required"}), 400
    file = request.files["audio"]
    if not file or file.filename == "":
        return jsonify({"error": "no file selected"}), 400

    allowed = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"error": f"nepodporovaný formát (povoleno: {', '.join(sorted(allowed))})"}), 400

    data = request.form
    job_id = q.create_job(
        label=data.get("label", ""),
        folder=data.get("folder", "Other"),
    )

    recordings_dir = os.path.join(cfg.DATA_DIR, "recordings")
    os.makedirs(recordings_dir, exist_ok=True)
    audio_path = os.path.join(recordings_dir, f"{job_id}{ext}")
    file.save(audio_path)

    q.update_job(
        job_id,
        audio_path=audio_path,
        recording_path=audio_path,
        template=data.get("template") or None,
        meeting_date=data.get("meeting_date") or None,
        scratch_notes=data.get("scratch_notes") or None,
    )
    q.set_status(job_id, "queued")

    tray = server._recording_service.tray
    if tray:
        tray.set_tooltip("FuseMark — Zpracovávám import")

    return jsonify({"job_id": job_id})


@bp.route("/jobs")
def route_jobs():
    jobs = q.list_jobs()
    for job in jobs:
        audio = job.get("audio_path") or job.get("recording_path")
        job["audio_exists"] = not audio or os.path.exists(audio)
    return jsonify(jobs)


@bp.route("/jobs", methods=["DELETE"])
def route_jobs_clear():
    q.clear_completed()
    return jsonify({"ok": True})


@bp.route("/jobs/<job_id>", methods=["DELETE"])
def route_job_delete(job_id):
    q.delete_job(job_id)
    return jsonify({"ok": True})


@bp.route("/jobs/<job_id>/retry", methods=["POST"])
def route_job_retry(job_id):
    job = q.get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "error":
        return jsonify({"error": "Job is not in error state"}), 400
    audio = job.get("audio_path") or job.get("recording_path")
    if audio and not os.path.exists(audio):
        return jsonify({"error": "Recording file has been deleted. This job cannot be retried."}), 409
    q.update_job(job_id, status="queued", error_message=None, retry_count=0)
    return jsonify({"ok": True})


@bp.route("/jobs/<job_id>/context", methods=["POST"])
def route_job_context(job_id):
    data = request.get_json(silent=True) or {}
    q.update_job(job_id, extra_context=data.get("context", ""))
    return jsonify({"ok": True})


@bp.route("/jobs/<job_id>/audio", methods=["POST"])
def route_job_audio(job_id):
    job = q.get_job(job_id)
    if job is None:
        return jsonify({"error": "Job not found"}), 404

    data = request.get_json(silent=True) or {}
    keep = 1 if data.get("keep") else 0

    if not keep and job["status"] not in ("done", "error"):
        return jsonify({"error": "Cannot delete audio for a job still in progress."}), 400

    q.update_job(job_id, keep_audio=keep)

    if not keep:
        audio = job.get("audio_path") or job.get("recording_path")
        if audio and os.path.exists(audio):
            os.remove(audio)

    return jsonify({"ok": True})
