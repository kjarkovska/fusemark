"""Settings persistence, autostart toggle, and Whisper model download/status."""

import os
import threading

from flask import Blueprint, jsonify, request

from app import config as cfg
from app import server

bp = Blueprint("settings_api", __name__)


@bp.route("/settings/save", methods=["POST"])
def route_settings_save():
    data = request.get_json(silent=True) or {}
    with cfg.lock():
        config = cfg.load()
        for key in ("vault_path", "whisper_model", "log_level", "default_template", "llm_provider", "ui_language"):
            if key in data:
                config[key] = data[key]
        for key in ("output_device", "input_device"):
            val = data.get(key)
            config[key] = int(val) if val not in (None, "", "null") else None
        lang_code = data.get("language")
        if lang_code:
            config["language"] = lang_code
            lang_entry = next((l for l in cfg.SUPPORTED_LANGUAGES if l["code"] == lang_code), None)
            if lang_entry:
                config["language_name"] = lang_entry["name"]
        if "auto_delete_recordings" in data:
            config["auto_delete_recordings"] = bool(data["auto_delete_recordings"])
        if "max_recordings_gb" in data:
            config["max_recordings_gb"] = float(data["max_recordings_gb"])
        if "check_updates" in data:
            config["check_updates"] = bool(data["check_updates"])
        if "glossary_suggestions" in data:
            config["glossary_suggestions"] = bool(data["glossary_suggestions"])
        cfg.save(config)
    return jsonify({"ok": True})


@bp.route("/autostart", methods=["GET"])
def route_autostart_status():
    from app.autostart import is_enabled
    return jsonify({"enabled": is_enabled()})


@bp.route("/autostart", methods=["POST"])
def route_autostart_set():
    from app.autostart import enable, disable
    data = request.get_json(silent=True) or {}
    if data.get("enabled"):
        enable()
    else:
        disable()
    return jsonify({"ok": True})


@bp.route("/api/model-status")
def route_model_status():
    from app.transcription.local import _model_is_downloaded
    config = cfg.load()
    model_dir = config.get("whisper_model_dir", "")
    out = {}
    for name, info in cfg.WHISPER_MODEL_SIZES.items():
        dl = server._dl.get(name, {})
        downloaded = _model_is_downloaded(model_dir, name)
        if downloaded:
            server._dl.pop(name, None)
        is_downloading = dl.get("downloading", False) and not downloaded
        downloaded_mb = 0
        if is_downloading:
            from app.transcription.local import _repo_id
            cache_name = "models--" + _repo_id(name).replace("/", "--")
            cache_path = os.path.join(model_dir, cache_name)
            downloaded_mb = round(server._dir_size_mb(cache_path))
        out[name] = {
            "downloaded": downloaded,
            "downloading": is_downloading,
            "downloaded_mb": downloaded_mb,
            "error": dl.get("error"),
            "disk_mb": info["disk_mb"],
        }
    return jsonify(out)


@bp.route("/api/download-model", methods=["POST"])
def route_download_model():
    from app.transcription.local import _model_is_downloaded
    data = request.get_json(silent=True) or {}
    name = data.get("model")
    if name not in cfg.WHISPER_MODEL_SIZES:
        return jsonify({"ok": False, "error": "Unknown model"}), 400
    config = cfg.load()
    model_dir = config.get("whisper_model_dir", "")
    if _model_is_downloaded(model_dir, name):
        return jsonify({"ok": True})
    if server._dl.get(name, {}).get("downloading"):
        return jsonify({"ok": True})
    server._dl[name] = {"downloading": True, "downloaded_mb": 0, "error": None}

    def _run():
        # Mutate server._dl (not a local binding) so tests that
        # monkeypatch.setattr(srv, "_dl", {...}) after this closure is
        # created still observe the write against the replaced dict.
        try:
            os.makedirs(model_dir, exist_ok=True)
            from faster_whisper.utils import download_model
            download_model(name, cache_dir=model_dir)
            server._dl[name] = {"downloading": False, "downloaded_mb": 0, "error": None}
        except Exception as exc:
            server._dl[name] = {"downloading": False, "downloaded_mb": 0, "error": str(exc)}

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


@bp.route("/api/languages")
def route_languages():
    return jsonify(cfg.SUPPORTED_LANGUAGES)


@bp.route("/api/templates")
def route_templates():
    config = cfg.load()
    from app.notes import list_templates
    return jsonify(list_templates(config.get("vault_path", "")))


@bp.route("/open-log", methods=["POST"])
def route_open_log():
    log_path = os.path.join(cfg.DATA_DIR, "logs", "fusemark.log")
    if not os.path.exists(log_path):
        return jsonify({"error": "Log file not found"}), 404
    os.startfile(log_path)
    return jsonify({"ok": True})
