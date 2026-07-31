"""Page shell routes: main UI and settings page."""

import os

from flask import Blueprint, redirect, render_template

from app import config as cfg
from app import server
from app.i18n import get_strings
from app.version import VERSION

bp = Blueprint("pages", __name__)


@bp.route("/")
def index():
    config = cfg.load()
    if not config.get("setup_complete"):
        return redirect("/wizard")
    vault_path = config.get("vault_path", "")
    folders = server._get_vault_folders(vault_path)
    from app.notes import list_templates
    templates = list_templates(vault_path)
    show_vault_warning = bool(config.get("setup_complete")) and not vault_path
    t = get_strings(config.get("ui_language", "en"))
    return render_template("index.html", config=config, folders=folders, templates=templates,
                           show_vault_warning=show_vault_warning, t=t)


@bp.route("/settings")
def settings():
    config = cfg.load()
    devices = server._get_devices()
    t = get_strings(config.get("ui_language", "en"))
    recordings_dir = os.path.join(cfg.DATA_DIR, "recordings")
    size_mb = round(server._recordings_size_mb(recordings_dir), 1)
    from app.transcription.local import _model_is_downloaded
    model_dir = config.get("whisper_model_dir", "")
    model_status = {
        name: {"downloaded": _model_is_downloaded(model_dir, name), "disk_mb": info["disk_mb"]}
        for name, info in cfg.WHISPER_MODEL_SIZES.items()
    }
    return render_template(
        "settings.html",
        config=config,
        devices=devices,
        t=t,
        version=VERSION,
        recordings_size_mb=size_mb,
        model_status=model_status,
    )
