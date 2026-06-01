import datetime
import json
from unittest.mock import MagicMock, patch

import pytest
import app.config as cfg
import app.updater as updater


# ------------------------------------------------------------------
# check_for_update
# ------------------------------------------------------------------

def test_check_skips_when_disabled(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "check_updates": False})
    with patch("urllib.request.urlopen") as mock_open:
        result = updater.check_for_update()
    mock_open.assert_not_called()
    assert result is None


def test_check_skips_within_throttle_window(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    recent = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cfg.save({**cfg.DEFAULTS, "check_updates": True,
              "last_update_check": recent, "latest_known_version": None})
    with patch("urllib.request.urlopen") as mock_open:
        result = updater.check_for_update()
    mock_open.assert_not_called()
    assert result is None


def test_check_force_bypasses_throttle(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    recent = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cfg.save({**cfg.DEFAULTS, "check_updates": True,
              "last_update_check": recent, "latest_known_version": None})
    payload = json.dumps({"tag_name": "v99.0.0", "html_url": "https://github.com/x/y"}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = updater.check_for_update(force=True)
    assert result is not None
    assert result["version"] == "99.0.0"


def test_check_returns_update_when_newer_available(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "check_updates": True})
    payload = json.dumps({"tag_name": "v99.0.0", "html_url": "https://github.com/x/y"}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = updater.check_for_update()
    assert result is not None
    assert result["version"] == "99.0.0"
    assert result["url"] == "https://github.com/x/y"


def test_check_returns_none_when_up_to_date(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "check_updates": True})
    from app.version import VERSION
    payload = json.dumps({"tag_name": f"v{VERSION}", "html_url": "https://github.com/x/y"}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = updater.check_for_update()
    assert result is None


def test_check_silent_on_network_error(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "check_updates": True})
    with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
        result = updater.check_for_update()
    assert result is None


# ------------------------------------------------------------------
# get_cached_status
# ------------------------------------------------------------------

def test_cached_status_available_when_newer(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "latest_known_version": "99.0.0",
              "latest_known_url": "https://github.com/x/y"})
    status = updater.get_cached_status()
    assert status["available"] is True
    assert status["version"] == "99.0.0"
    assert status["url"] == "https://github.com/x/y"


def test_cached_status_not_available_when_same_version(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    from app.version import VERSION
    cfg.save({**cfg.DEFAULTS, "latest_known_version": VERSION})
    status = updater.get_cached_status()
    assert status["available"] is False


def test_cached_status_not_available_when_no_cached_version(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS})
    status = updater.get_cached_status()
    assert status["available"] is False
    assert status["version"] == ""


# ------------------------------------------------------------------
# /update-status route
# ------------------------------------------------------------------

def test_update_status_route_shape(flask_client):
    r = flask_client.get("/update-status")
    assert r.status_code == 200
    data = r.get_json()
    assert "available" in data
    assert "version" in data
    assert "url" in data


def test_update_status_route_not_available_by_default(flask_client):
    r = flask_client.get("/update-status")
    assert r.get_json()["available"] is False


# ------------------------------------------------------------------
# /open-url route
# ------------------------------------------------------------------

def test_open_url_rejects_non_https(flask_client):
    import json as _json
    r = flask_client.post(
        "/open-url",
        data=_json.dumps({"url": "http://example.com"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_open_url_calls_webbrowser(flask_client):
    import json as _json
    with patch("webbrowser.open") as mock_open:
        r = flask_client.post(
            "/open-url",
            data=_json.dumps({"url": "https://github.com/x/y/releases"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_open.assert_called_once_with("https://github.com/x/y/releases")
