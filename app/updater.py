import datetime
import json
import logging
import urllib.error
import urllib.request

from app import config as cfg
from app.version import VERSION

logger = logging.getLogger(__name__)

RELEASES_URL = "https://api.github.com/repos/kjarkovska/note-taker/releases/latest"
_THROTTLE_HOURS = 24


def _parse_version(v: str) -> tuple:
    return tuple(int(x) for x in v.lstrip("v").split("."))


def check_for_update(force: bool = False) -> dict | None:
    """Check GitHub for a newer release. Returns {version, url} or None.

    Silent on network errors. Respects check_updates config flag and 24h
    throttle unless force=True.
    """
    config = cfg.load()

    if not force and not config.get("check_updates", True):
        return None

    if not force:
        last = config.get("last_update_check")
        if last:
            try:
                last_dt = datetime.datetime.fromisoformat(last)
                if last_dt.tzinfo is None:
                    last_dt = last_dt.replace(tzinfo=datetime.timezone.utc)
                age = datetime.datetime.now(datetime.timezone.utc) - last_dt
                if age.total_seconds() < _THROTTLE_HOURS * 3600:
                    cached = get_cached_status()
                    if cached["available"]:
                        return {"version": cached["version"], "url": cached["url"]}
                    return None
            except (ValueError, TypeError):
                pass

    try:
        req = urllib.request.Request(
            RELEASES_URL,
            headers={"User-Agent": f"FuseMark/{VERSION}"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        latest = data["tag_name"].lstrip("v")
        url = data.get("html_url", "")
        update_available = _parse_version(latest) > _parse_version(VERSION)
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        config = cfg.load()
        config["last_update_check"] = now
        config["latest_known_version"] = latest
        config["latest_known_url"] = url
        cfg.save(config)
        return {"version": latest, "url": url} if update_available else None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # No releases published yet — record the check time and return no update
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            config = cfg.load()
            config["last_update_check"] = now
            cfg.save(config)
            return None
        logger.debug("Update check HTTP error %s", exc.code, exc_info=True)
        return None
    except Exception:
        logger.debug("Update check failed", exc_info=True)
        return None


def get_cached_status() -> dict:
    """Return cached update status without a network call."""
    config = cfg.load()
    latest = config.get("latest_known_version")
    if not latest:
        return {"available": False, "version": "", "url": ""}
    try:
        available = _parse_version(latest) > _parse_version(VERSION)
    except (ValueError, TypeError):
        available = False
    return {
        "available": available,
        "version": latest,
        "url": config.get("latest_known_url", ""),
    }
