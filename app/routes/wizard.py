"""First-run setup wizard: LLM test, test recording, vault folder browse, completion."""

import logging
import os

from flask import Blueprint, jsonify, redirect, render_template, request, send_file

from app import config as cfg
from app import server
from app.exceptions import LLMAuthError, LLMRateLimitError
from app.i18n import get_strings

bp = Blueprint("wizard", __name__)

logger = logging.getLogger(__name__)


@bp.route("/wizard")
def wizard():
    config = cfg.load()
    if config.get("setup_complete"):
        return redirect("/")
    devices = server._get_devices()
    t = get_strings(config.get("ui_language", "en"))
    return render_template("wizard.html", config=config, devices=devices, t=t)


@bp.route("/wizard/test-llm", methods=["POST"])
def wizard_test_llm():
    data = request.get_json(silent=True) or {}
    provider = data.get("provider", "").strip()
    key = data.get("key", "").strip()
    if not key:
        return jsonify({"ok": False, "error": "No key provided"}), 400
    try:
        if provider == "anthropic":
            from app.llm.anthropic_provider import test_connection
        elif provider == "openai":
            from app.llm.openai_provider import test_connection
        elif provider == "mistral":
            from app.llm.mistral_provider import test_connection
        else:
            return jsonify({"ok": False, "error": f"Unknown provider: {provider}"}), 400
        test_connection(key)
        return jsonify({"ok": True})
    except LLMAuthError as exc:
        return jsonify({"ok": False, "error": str(exc)})
    except LLMRateLimitError as exc:
        return jsonify({"ok": False, "error": str(exc)})
    except Exception:
        logger.exception("Wizard LLM test failed")
        return jsonify({"ok": False, "error": "Connection test failed"})


@bp.route("/wizard/test-recording", methods=["POST"])
def wizard_test_recording():
    """Record 5 seconds; return filename. Blocks for the full 5s — UI must show spinner."""
    if server._recording_service.is_recording:
        return jsonify({"error": "Cannot test recording while a meeting is being recorded."}), 409

    config = cfg.load()
    recordings_dir = os.path.join(cfg.DATA_DIR, "recordings")
    os.makedirs(recordings_dir, exist_ok=True)
    filename = f"wizard_test_{int(server._time.time())}.mp3"
    filepath = os.path.join(recordings_dir, filename)
    r = server.Recorder(
        output_device=config.get("output_device"),
        input_device=config.get("input_device"),
    )
    try:
        r.start()
        server._time.sleep(5)
        r.stop()
        r.save(filepath)
    except Exception as exc:
        logger.exception("Wizard test recording failed")
        r.stop()
        return jsonify({"error": str(exc)}), 500
    return jsonify({"filename": filename})


@bp.route("/wizard/playback/<filename>")
def wizard_playback(filename):
    """Serve a temp recording for in-browser audio playback."""
    if "/" in filename or os.sep in filename or ".." in filename:
        return jsonify({"error": "Invalid filename"}), 403
    filepath = os.path.join(cfg.DATA_DIR, "recordings", filename)
    if not os.path.isfile(filepath):
        return jsonify({"error": "Not found"}), 404
    return send_file(filepath, mimetype="audio/mpeg")


@bp.route("/wizard/browse-folder", methods=["POST"])
def wizard_browse_folder():
    try:
        import webview
        windows = webview.windows
        if not windows:
            raise RuntimeError("no window")
        result = windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        path = result[0] if result else ""
        return jsonify({"path": path})
    except Exception:
        _t = get_strings(cfg.load().get("ui_language", "en"))
        return jsonify({
            "path": "",
            "dev_mode": True,
            "message": _t.get("wizard_folder_dev_mode", "Folder browser unavailable — type the path manually."),
        }), 200


@bp.route("/wizard/complete", methods=["POST"])
def wizard_complete():
    data = request.get_json(silent=True) or {}
    config = cfg.load()
    provider = data.get("llm_provider", "anthropic")
    key = (data.get("llm_key") or "").strip()
    if key:
        if provider == "anthropic":
            from app.llm.anthropic_provider import set_api_key
            set_api_key(key)
        elif provider == "openai":
            from app.llm.openai_provider import set_api_key
            set_api_key(key)
        elif provider == "mistral":
            from app.llm.mistral_provider import set_api_key
            set_api_key(key)
    for field in ("llm_provider", "whisper_model", "vault_path"):
        if field in data:
            config[field] = data[field]
    for field in ("output_device", "input_device"):
        val = data.get(field)
        config[field] = int(val) if val not in (None, "", "null") else None
    config["setup_complete"] = True
    cfg.save(config)
    return jsonify({"ok": True})


@bp.route("/wizard/reset", methods=["POST"])
def wizard_reset():
    config = cfg.load()
    config["setup_complete"] = False
    cfg.save(config)
    return jsonify({"ok": True})
