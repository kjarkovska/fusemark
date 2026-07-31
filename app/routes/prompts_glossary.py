"""Open the glossary/prompts folders in the OS shell; report prompt override status."""

from flask import Blueprint, jsonify

bp = Blueprint("prompts_glossary", __name__)


@bp.route("/open-glossary", methods=["POST"])
def route_open_glossary():
    from app.glossary import open_glossary
    open_glossary()
    return jsonify({"ok": True})


@bp.route("/open-prompts-folder", methods=["POST"])
def route_open_prompts_folder():
    from app.prompts import open_prompts_folder
    open_prompts_folder()
    return jsonify({"ok": True})


@bp.route("/api/prompts-status", methods=["GET"])
def route_prompts_status():
    from app.prompts import validate_user_prompts
    return jsonify(validate_user_prompts())
