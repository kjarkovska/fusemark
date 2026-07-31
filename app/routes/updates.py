"""Update check (GitHub releases), cached status, and open-in-browser."""

import datetime
import logging
import urllib.error

from flask import Blueprint, jsonify, request

from app import config as cfg
from app.version import VERSION

bp = Blueprint("updates", __name__)

logger = logging.getLogger(__name__)


@bp.route("/update-check", methods=["POST"])
def update_check_route():
    import app.updater as updater
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        latest, url = updater._fetch_latest_release()
        update_available = updater._parse_version(latest) > updater._parse_version(VERSION)
        with cfg.lock():
            config = cfg.load()
            config["last_update_check"] = now
            config["latest_known_version"] = latest
            config["latest_known_url"] = url
            cfg.save(config)
        return jsonify({"ok": True, "update_available": update_available,
                        "version": latest, "url": url, "checked_at": now})
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # No releases published yet — not an error
            with cfg.lock():
                config = cfg.load()
                config["last_update_check"] = now
                cfg.save(config)
            return jsonify({"ok": True, "update_available": False,
                            "version": "", "url": "", "checked_at": now})
        logger.warning("Update check HTTP error %s", exc.code)
        return jsonify({"ok": False, "error": "Update check failed"}), 500
    except Exception:
        logger.exception("Update check failed")
        return jsonify({"ok": False, "error": "Update check failed"}), 500


@bp.route("/update-status", methods=["GET"])
def update_status_route():
    import app.updater as updater
    if not cfg.load().get("check_updates", True):
        return jsonify({"available": False, "version": "", "url": ""})
    return jsonify(updater.get_cached_status())


@bp.route("/open-url", methods=["POST"])
def open_url_route():
    import webbrowser
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url.startswith("https://"):
        return jsonify({"error": "Invalid URL"}), 400
    webbrowser.open(url)
    return jsonify({"ok": True})
