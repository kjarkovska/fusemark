import io
import json
import threading
from unittest.mock import MagicMock, patch

import pytest
import app.queue as q


# ------------------------------------------------------------------
# Basic routes
# ------------------------------------------------------------------

def test_index_ok(flask_client):
    r = flask_client.get("/")
    assert r.status_code == 200


def test_status_not_recording(flask_client):
    r = flask_client.get("/status")
    data = r.get_json()
    assert data["recording"] is False
    assert data["job_id"] is None


def test_jobs_empty(flask_client):
    r = flask_client.get("/jobs")
    assert r.status_code == 200
    assert r.get_json() == []


def test_delete_jobs_empty_queue(flask_client):
    r = flask_client.delete("/jobs")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_templates_empty_dir(flask_client):
    r = flask_client.get("/api/templates")
    assert r.status_code == 200
    assert r.get_json() == []


def test_templates_lists_files(flask_client, tmp_vault):
    (tmp_vault / "ObsiNote" / "Templates" / "Meeting.md").write_text("t", encoding="utf-8")
    (tmp_vault / "ObsiNote" / "Templates" / "Standup.md").write_text("t", encoding="utf-8")
    r = flask_client.get("/api/templates")
    assert r.get_json() == ["Meeting", "Standup"]


# ------------------------------------------------------------------
# Import transcript
# ------------------------------------------------------------------

def test_import_empty_body(flask_client):
    r = flask_client.post(
        "/import-transcript",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "transcript required" in r.get_json()["error"]


def test_import_blank_transcript(flask_client):
    r = flask_client.post(
        "/import-transcript",
        data=json.dumps({"transcript": "   "}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_import_creates_job(flask_client):
    r = flask_client.post(
        "/import-transcript",
        data=json.dumps({"transcript": "Ahoj světe.", "label": "Test Meeting"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert "job_id" in data
    job = q.get_job(data["job_id"])
    assert job["status"] == "queued"
    assert job["transcript"] == "Ahoj světe."
    assert job["label"] == "Test Meeting"


def test_import_stores_meeting_date(flask_client):
    r = flask_client.post(
        "/import-transcript",
        data=json.dumps({"transcript": "text", "meeting_date": "2025-01-15"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    job = q.get_job(r.get_json()["job_id"])
    assert job["meeting_date"] == "2025-01-15"


def test_import_stores_template(flask_client):
    r = flask_client.post(
        "/import-transcript",
        data=json.dumps({"transcript": "text", "template": "Meeting"}),
        content_type="application/json",
    )
    job = q.get_job(r.get_json()["job_id"])
    assert job["template"] == "Meeting"


def test_import_empty_template_stored_as_null(flask_client):
    r = flask_client.post(
        "/import-transcript",
        data=json.dumps({"transcript": "text", "template": ""}),
        content_type="application/json",
    )
    job = q.get_job(r.get_json()["job_id"])
    assert job["template"] is None


# ------------------------------------------------------------------
# Import audio
# ------------------------------------------------------------------

def test_import_audio_missing_file(flask_client):
    r = flask_client.post("/import-audio", data={})
    assert r.status_code == 400
    assert "audio file required" in r.get_json()["error"]


def test_import_audio_bad_extension(flask_client):
    data = {"audio": (io.BytesIO(b"data"), "recording.exe")}
    r = flask_client.post("/import-audio", data=data, content_type="multipart/form-data")
    assert r.status_code == 400
    assert "nepodporovaný formát" in r.get_json()["error"]


def test_import_audio_success(flask_client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    audio_bytes = io.BytesIO(b"\xff\xfb\x90\x00" * 100)
    data = {
        "audio": (audio_bytes, "meeting.mp3"),
        "label": "Standup",
        "scratch_notes": "Discussed roadmap",
    }
    r = flask_client.post("/import-audio", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    job_id = r.get_json()["job_id"]
    job = q.get_job(job_id)
    assert job["status"] == "queued"
    assert job["audio_path"].endswith(".mp3")
    assert job["scratch_notes"] == "Discussed roadmap"
    assert job["label"] == "Standup"


def test_import_audio_no_scratch_notes(flask_client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    data = {"audio": (io.BytesIO(b"\x00" * 16), "clip.wav")}
    r = flask_client.post("/import-audio", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    job = q.get_job(r.get_json()["job_id"])
    assert not job["scratch_notes"]


# ------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------

def test_settings_save_ok(flask_client):
    r = flask_client.post(
        "/settings/save",
        data=json.dumps({"whisper_model": "small", "log_level": "INFO"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_settings_save_default_template(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    flask_client.post(
        "/settings/save",
        data=json.dumps({"default_template": "Meeting"}),
        content_type="application/json",
    )
    loaded = cfg.load()
    assert loaded["default_template"] == "Meeting"


# ------------------------------------------------------------------
# Job management
# ------------------------------------------------------------------

def test_delete_single_job(flask_client):
    job_id = q.create_job(label="finished")
    q.set_status(job_id, "queued")
    q.set_status(job_id, "done")
    r = flask_client.delete(f"/jobs/{job_id}")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert q.get_job(job_id) is None


def test_update_job_context(flask_client):
    job_id = q.create_job()
    r = flask_client.post(
        f"/jobs/{job_id}/context",
        data=json.dumps({"context": "extra info"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert q.get_job(job_id)["extra_context"] == "extra info"


def test_job_audio_keep_false_no_file(flask_client):
    job_id = q.create_job()
    r = flask_client.post(
        f"/jobs/{job_id}/audio",
        data=json.dumps({"keep": False}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_languages_returns_list(flask_client):
    r = flask_client.get("/api/languages")
    assert r.status_code == 200
    langs = r.get_json()
    assert isinstance(langs, list)
    codes = {l["code"] for l in langs}
    assert "cs" in codes
    assert "en" in codes
    assert "auto" in codes


def test_languages_entries_have_code_and_name(flask_client):
    langs = flask_client.get("/api/languages").get_json()
    for entry in langs:
        assert "code" in entry and "name" in entry


def test_settings_save_llm_provider(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    flask_client.post(
        "/settings/save",
        data=json.dumps({"llm_provider": "openai"}),
        content_type="application/json",
    )
    assert cfg.load()["llm_provider"] == "openai"


def test_settings_save_language_updates_name(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    flask_client.post(
        "/settings/save",
        data=json.dumps({"language": "en"}),
        content_type="application/json",
    )
    loaded = cfg.load()
    assert loaded["language"] == "en"
    assert loaded["language_name"] == "English"


def test_settings_save_auto_detect_language(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    flask_client.post(
        "/settings/save",
        data=json.dumps({"language": "auto"}),
        content_type="application/json",
    )
    loaded = cfg.load()
    assert loaded["language"] == "auto"
    assert loaded["language_name"] == "Auto-detect"


def test_api_key_unknown_provider_returns_400(flask_client):
    r = flask_client.post(
        "/api-key",
        data=json.dumps({"key": "sk-test", "provider": "grok"}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "Unknown provider" in r.get_json()["error"]


def test_api_key_no_key_returns_400(flask_client):
    r = flask_client.post(
        "/api-key",
        data=json.dumps({"key": "", "provider": "anthropic"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_api_key_anthropic_saved(flask_client):
    from unittest.mock import patch
    with patch("app.llm.anthropic_provider.keyring.set_password") as mock_set:
        r = flask_client.post(
            "/api-key",
            data=json.dumps({"key": "sk-ant-test", "provider": "anthropic"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    mock_set.assert_called_once_with("ObsiNote-Anthropic", "api_key", "sk-ant-test")


def test_api_key_openai_saved(flask_client):
    from unittest.mock import patch
    with patch("app.llm.openai_provider.keyring.set_password") as mock_set:
        r = flask_client.post(
            "/api-key",
            data=json.dumps({"key": "sk-openai-test", "provider": "openai"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_set.assert_called_once_with("ObsiNote-OpenAI", "api_key", "sk-openai-test")


def test_api_key_mistral_saved(flask_client):
    from unittest.mock import patch
    with patch("app.llm.mistral_provider.keyring.set_password") as mock_set:
        r = flask_client.post(
            "/api-key",
            data=json.dumps({"key": "ms-test", "provider": "mistral"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_set.assert_called_once_with("ObsiNote-Mistral", "api_key", "ms-test")


def test_jobs_list_after_import(flask_client):
    flask_client.post(
        "/import-transcript",
        data=json.dumps({"transcript": "one"}),
        content_type="application/json",
    )
    flask_client.post(
        "/import-transcript",
        data=json.dumps({"transcript": "two"}),
        content_type="application/json",
    )
    jobs = flask_client.get("/jobs").get_json()
    assert len(jobs) == 2


# ------------------------------------------------------------------
# audio_exists field in /jobs
# ------------------------------------------------------------------

def test_jobs_audio_exists_true_when_no_audio(flask_client):
    job_id = q.create_job()
    jobs = flask_client.get("/jobs").get_json()
    job = next(j for j in jobs if j["id"] == job_id)
    assert job["audio_exists"] is True


def test_jobs_audio_exists_true_when_file_present(flask_client, tmp_path):
    audio = tmp_path / "rec.mp3"
    audio.write_bytes(b"")
    job_id = q.create_job()
    q.update_job(job_id, audio_path=str(audio))
    jobs = flask_client.get("/jobs").get_json()
    job = next(j for j in jobs if j["id"] == job_id)
    assert job["audio_exists"] is True


def test_jobs_audio_exists_false_when_file_missing(flask_client, tmp_path):
    job_id = q.create_job()
    q.update_job(job_id, audio_path=str(tmp_path / "gone.mp3"))
    jobs = flask_client.get("/jobs").get_json()
    job = next(j for j in jobs if j["id"] == job_id)
    assert job["audio_exists"] is False


# ------------------------------------------------------------------
# POST /jobs/<id>/retry
# ------------------------------------------------------------------

def test_retry_unknown_job_returns_404(flask_client):
    r = flask_client.post("/jobs/nonexistent-id/retry")
    assert r.status_code == 404


def test_retry_non_error_job_returns_400(flask_client):
    job_id = q.create_job()
    q.set_status(job_id, "queued")
    r = flask_client.post(f"/jobs/{job_id}/retry")
    assert r.status_code == 400


def test_retry_missing_audio_returns_409(flask_client, tmp_path):
    job_id = q.create_job()
    q.update_job(job_id, status="error", error_message="oops",
                 audio_path=str(tmp_path / "gone.mp3"))
    r = flask_client.post(f"/jobs/{job_id}/retry")
    assert r.status_code == 409
    assert "deleted" in r.get_json()["error"].lower()


def test_retry_success_requeues_job(flask_client, tmp_path):
    audio = tmp_path / "rec.mp3"
    audio.write_bytes(b"")
    job_id = q.create_job()
    q.update_job(job_id, status="error", error_message="bad key",
                 audio_path=str(audio))
    r = flask_client.post(f"/jobs/{job_id}/retry")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    refreshed = q.get_job(job_id)
    assert refreshed["status"] == "queued"
    assert refreshed["error_message"] is None


def test_retry_import_job_no_audio_succeeds(flask_client):
    job_id = q.create_job()
    q.update_job(job_id, status="error", error_message="api error")
    r = flask_client.post(f"/jobs/{job_id}/retry")
    assert r.status_code == 200
    assert q.get_job(job_id)["status"] == "queued"


# ------------------------------------------------------------------
# Vault warning on index page
# ------------------------------------------------------------------

def test_index_shows_vault_warning_when_setup_complete_no_vault(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "setup_complete": True, "vault_path": ""})
    r = flask_client.get("/")
    assert b"Output folder not configured" in r.data


def test_index_no_vault_warning_when_vault_set(flask_client, tmp_path, monkeypatch, tmp_vault):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "setup_complete": True, "vault_path": str(tmp_vault)})
    r = flask_client.get("/")
    assert b'class="warning-banner"' not in r.data


# ------------------------------------------------------------------
# POST /start — recording control
# ------------------------------------------------------------------

def test_start_route_creates_job(flask_client, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_recorder", None)
    monkeypatch.setattr(srv, "_current_job_id", None)
    mock_rec = MagicMock()
    with patch("app.server.Recorder", return_value=mock_rec):
        r = flask_client.post(
            "/start",
            data=json.dumps({"label": "Stand-up", "folder": "Other"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    job_id = r.get_json()["job_id"]
    assert q.get_job(job_id)["label"] == "Stand-up"
    mock_rec.start.assert_called_once()


def test_start_route_already_recording_returns_400(flask_client, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_recorder", MagicMock())
    r = flask_client.post("/start", data=json.dumps({}), content_type="application/json")
    assert r.status_code == 400


def test_start_route_saves_template(flask_client, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_recorder", None)
    monkeypatch.setattr(srv, "_current_job_id", None)
    with patch("app.server.Recorder", return_value=MagicMock()):
        r = flask_client.post(
            "/start",
            data=json.dumps({"label": "x", "template": "Meeting"}),
            content_type="application/json",
        )
    job_id = r.get_json()["job_id"]
    assert q.get_job(job_id)["template"] == "Meeting"


# ------------------------------------------------------------------
# POST /stop — recording control
# ------------------------------------------------------------------

def test_stop_route_not_recording_returns_400(flask_client, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_recorder", None)
    r = flask_client.post("/stop", data=json.dumps({}), content_type="application/json")
    assert r.status_code == 400


def test_stop_route_success(flask_client, monkeypatch, tmp_path):
    import app.server as srv
    import app.config as cfg
    job_id = q.create_job(label="Stop test")
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(srv, "_recorder", MagicMock())
    monkeypatch.setattr(srv, "_current_job_id", job_id)
    r = flask_client.post("/stop", data=json.dumps({}), content_type="application/json")
    assert r.status_code == 200
    assert r.get_json()["job_id"] == job_id
    assert q.get_job(job_id)["status"] == "queued"


# ------------------------------------------------------------------
# GET /settings
# ------------------------------------------------------------------

def test_settings_route_ok(flask_client, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_get_devices", lambda: [])
    r = flask_client.get("/settings")
    assert r.status_code == 200


# ------------------------------------------------------------------
# Autostart routes
# ------------------------------------------------------------------

def test_autostart_get_returns_enabled_state(flask_client):
    with patch("app.autostart.is_enabled", return_value=True):
        r = flask_client.get("/autostart")
    assert r.status_code == 200
    assert r.get_json()["enabled"] is True


def test_autostart_post_enable(flask_client):
    with patch("app.autostart.enable") as mock_en, \
         patch("app.autostart.disable") as mock_dis:
        r = flask_client.post(
            "/autostart",
            data=json.dumps({"enabled": True}),
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_en.assert_called_once()
    mock_dis.assert_not_called()


def test_autostart_post_disable(flask_client):
    with patch("app.autostart.enable") as mock_en, \
         patch("app.autostart.disable") as mock_dis:
        r = flask_client.post(
            "/autostart",
            data=json.dumps({"enabled": False}),
            content_type="application/json",
        )
    assert r.status_code == 200
    mock_dis.assert_called_once()
    mock_en.assert_not_called()


# ------------------------------------------------------------------
# Open-glossary and open-log routes
# ------------------------------------------------------------------

def test_open_glossary_route(flask_client):
    with patch("app.glossary.open_in_obsidian") as mock_open:
        r = flask_client.post("/open-glossary")
    assert r.status_code == 200
    mock_open.assert_called_once()


def test_open_log_not_found_returns_404(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    r = flask_client.post("/open-log")
    assert r.status_code == 404


def test_open_log_found_calls_startfile(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "obsinote.log").write_text("log content")
    with patch("app.server.os.startfile") as mock_sf:
        r = flask_client.post("/open-log")
    assert r.status_code == 200
    mock_sf.assert_called_once()


# ------------------------------------------------------------------
# keep_audio=False deletes existing audio file
# ------------------------------------------------------------------

def test_job_audio_keep_false_deletes_existing_file(flask_client, tmp_path):
    audio = tmp_path / "rec.mp3"
    audio.write_bytes(b"audio data")
    job_id = q.create_job()
    q.update_job(job_id, audio_path=str(audio))
    r = flask_client.post(
        f"/jobs/{job_id}/audio",
        data=json.dumps({"keep": False}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert not audio.exists()


# ------------------------------------------------------------------
# /api/model-status
# ------------------------------------------------------------------

def test_model_status_not_downloaded(flask_client, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_dl", {})
    with patch("app.transcription.local._model_is_downloaded", return_value=False):
        r = flask_client.get("/api/model-status")
    assert r.status_code == 200
    data = r.get_json()
    assert "large-v3-turbo" in data
    entry = data["large-v3-turbo"]
    assert entry["downloaded"] is False
    assert entry["downloading"] is False
    assert entry["error"] is None
    assert "disk_mb" in entry


def test_model_status_downloaded(flask_client, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_dl", {})
    with patch("app.transcription.local._model_is_downloaded", return_value=True):
        r = flask_client.get("/api/model-status")
    data = r.get_json()
    assert data["large-v3-turbo"]["downloaded"] is True
    assert data["large-v3-turbo"]["downloading"] is False


def test_model_status_downloading_shows_mb(flask_client, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_dl", {
        "large-v3-turbo": {"downloading": True, "downloaded_mb": 0, "error": None},
    })
    monkeypatch.setattr(srv, "_dir_size_mb", lambda path: 350.0)
    with patch("app.transcription.local._model_is_downloaded", return_value=False):
        r = flask_client.get("/api/model-status")
    entry = r.get_json()["large-v3-turbo"]
    assert entry["downloading"] is True
    assert entry["downloaded_mb"] == 350


def test_model_status_clears_dl_when_downloaded(flask_client, monkeypatch):
    import app.server as srv
    dl = {"large-v3-turbo": {"downloading": False, "downloaded_mb": 0, "error": None}}
    monkeypatch.setattr(srv, "_dl", dl)
    with patch("app.transcription.local._model_is_downloaded", return_value=True):
        flask_client.get("/api/model-status")
    assert "large-v3-turbo" not in dl


# ------------------------------------------------------------------
# /api/download-model
# ------------------------------------------------------------------

def test_download_model_unknown_returns_400(flask_client):
    r = flask_client.post(
        "/api/download-model",
        data=json.dumps({"model": "nonexistent"}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_download_model_already_downloading_is_idempotent(flask_client, monkeypatch):
    import app.server as srv
    dl = {"large-v3-turbo": {"downloading": True, "downloaded_mb": 0, "error": None}}
    monkeypatch.setattr(srv, "_dl", dl)
    with patch("app.transcription.local._model_is_downloaded", return_value=False):
        r = flask_client.post(
            "/api/download-model",
            data=json.dumps({"model": "large-v3-turbo"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert dl["large-v3-turbo"]["downloading"] is True  # untouched


def test_download_model_starts_background_download(flask_client, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_dl", {})
    called = threading.Event()

    def fake_download(*args, **kwargs):
        called.set()

    with patch("app.transcription.local._model_is_downloaded", return_value=False), \
         patch("faster_whisper.utils.download_model", side_effect=fake_download):
        r = flask_client.post(
            "/api/download-model",
            data=json.dumps({"model": "large-v3-turbo"}),
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert called.wait(timeout=3), "download_model was never called in background thread"


# ------------------------------------------------------------------
# ui_language — P5.5
# ------------------------------------------------------------------

def test_default_config_has_ui_language_en():
    from app.config import DEFAULTS
    assert DEFAULTS.get("ui_language") == "en"


def test_settings_save_ui_language(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    r = flask_client.post(
        "/settings/save",
        data=json.dumps({"ui_language": "cs"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    config = cfg.load()
    assert config["ui_language"] == "cs"


# ------------------------------------------------------------------
# P6 — Wizard routes
# ------------------------------------------------------------------

def _wizard_client(flask_client, tmp_path, monkeypatch, setup_complete):
    """Helper: write config with given setup_complete value, return flask_client."""
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "setup_complete": setup_complete, "vault_path": str(tmp_path)})
    return flask_client


def test_index_redirects_to_wizard_when_not_complete(flask_client, tmp_path, monkeypatch):
    _wizard_client(flask_client, tmp_path, monkeypatch, setup_complete=False)
    r = flask_client.get("/")
    assert r.status_code == 302
    assert "/wizard" in r.headers["Location"]


def test_index_served_when_setup_complete(flask_client, tmp_path, monkeypatch):
    _wizard_client(flask_client, tmp_path, monkeypatch, setup_complete=True)
    r = flask_client.get("/")
    assert r.status_code == 200


def test_wizard_page_served_when_not_complete(flask_client, tmp_path, monkeypatch):
    import app.server as srv
    monkeypatch.setattr(srv, "_get_devices", lambda: [])
    _wizard_client(flask_client, tmp_path, monkeypatch, setup_complete=False)
    r = flask_client.get("/wizard")
    assert r.status_code == 200
    assert b"wizard" in r.data.lower()


def test_wizard_redirects_to_index_when_complete(flask_client, tmp_path, monkeypatch):
    _wizard_client(flask_client, tmp_path, monkeypatch, setup_complete=True)
    r = flask_client.get("/wizard")
    assert r.status_code == 302
    assert r.headers["Location"].rstrip("/").endswith("/") or "/" in r.headers["Location"]


def test_wizard_test_llm_missing_key_returns_400(flask_client):
    r = flask_client.post(
        "/wizard/test-llm",
        data=json.dumps({"provider": "anthropic", "key": ""}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_wizard_test_llm_unknown_provider_returns_400(flask_client):
    r = flask_client.post(
        "/wizard/test-llm",
        data=json.dumps({"provider": "grok", "key": "sk-test"}),
        content_type="application/json",
    )
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_wizard_test_llm_auth_error_returns_ok_false(flask_client):
    from app.exceptions import LLMAuthError
    with patch("app.llm.anthropic_provider.test_connection", side_effect=LLMAuthError("bad key")):
        r = flask_client.post(
            "/wizard/test-llm",
            data=json.dumps({"provider": "anthropic", "key": "sk-bad"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is False
    assert "bad key" in data["error"]


def test_wizard_test_llm_success_returns_ok_true(flask_client):
    with patch("app.llm.anthropic_provider.test_connection", return_value=None):
        r = flask_client.post(
            "/wizard/test-llm",
            data=json.dumps({"provider": "anthropic", "key": "sk-valid"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_wizard_test_recording_returns_filename(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    mock_rec.save.side_effect = lambda path: open(path, "wb").close()
    with patch("app.server.Recorder", return_value=mock_rec), \
         patch("app.server._time", MagicMock(time=lambda: 12345, sleep=lambda n: None)):
        r = flask_client.post("/wizard/test-recording")
    assert r.status_code == 200
    data = r.get_json()
    assert "filename" in data
    assert data["filename"].startswith("wizard_test_")


def test_wizard_playback_serves_file(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir()
    (recordings_dir / "wizard_test_123.mp3").write_bytes(b"fakeaudio")
    r = flask_client.get("/wizard/playback/wizard_test_123.mp3")
    assert r.status_code == 200


def test_wizard_playback_path_traversal_blocked(flask_client):
    # Flask normalizes ../config.json before routing; test with a filename that
    # contains ".." as a substring but no slash so Flask passes it to the handler.
    r = flask_client.get("/wizard/playback/..config.json")
    assert r.status_code == 403


def test_wizard_browse_folder_dev_fallback(flask_client):
    r = flask_client.post("/wizard/browse-folder")
    assert r.status_code == 200
    data = r.get_json()
    assert data["dev_mode"] is True
    assert "path" in data


def test_wizard_complete_sets_setup_complete(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "setup_complete": False})
    with patch("app.llm.anthropic_provider.keyring.set_password"):
        r = flask_client.post(
            "/wizard/complete",
            data=json.dumps({
                "llm_provider": "anthropic",
                "llm_key": "sk-ant-test",
                "whisper_model": "large-v3-turbo",
                "vault_path": str(tmp_path / "notes"),
            }),
            content_type="application/json",
        )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    saved = cfg.load()
    assert saved["setup_complete"] is True
    assert saved["vault_path"] == str(tmp_path / "notes")
    assert saved["llm_provider"] == "anthropic"


def test_wizard_reset_sets_setup_complete_false(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "setup_complete": True})
    r = flask_client.post("/wizard/reset")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert cfg.load()["setup_complete"] is False


# ------------------------------------------------------------------
# P7 — Recordings size + cleanup
# ------------------------------------------------------------------

def test_recordings_size_no_dir_returns_zero(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    r = flask_client.get("/recordings/size")
    assert r.status_code == 200
    data = r.get_json()
    assert data["size_mb"] == 0


def test_recordings_size_sums_mp3s(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    rdir = tmp_path / "recordings"
    rdir.mkdir()
    (rdir / "a.mp3").write_bytes(b"x" * 1024 * 512)  # 0.5 MB
    (rdir / "b.mp3").write_bytes(b"x" * 1024 * 512)  # 0.5 MB
    (rdir / "c.txt").write_bytes(b"x" * 1024 * 1024)  # ignored
    r = flask_client.get("/recordings/size")
    data = r.get_json()
    assert data["size_mb"] == 1.0


def test_recordings_cleanup_deletes_done_job_files(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    rdir = tmp_path / "recordings"
    rdir.mkdir()
    mp3 = rdir / "done_job.mp3"
    mp3.write_bytes(b"audio")
    job_id = q.create_job(label="test")
    q.update_job(job_id, audio_path=str(mp3))
    q.set_status(job_id, "queued")
    q.set_status(job_id, "done")
    r = flask_client.post("/recordings/cleanup")
    assert r.status_code == 200
    data = r.get_json()
    assert data["deleted"] == 1
    assert not mp3.exists()


def test_recordings_cleanup_keeps_active_job_files(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    rdir = tmp_path / "recordings"
    rdir.mkdir()
    mp3 = rdir / "active_job.mp3"
    mp3.write_bytes(b"audio")
    job_id = q.create_job(label="active")
    q.update_job(job_id, audio_path=str(mp3))
    q.set_status(job_id, "queued")
    r = flask_client.post("/recordings/cleanup")
    assert r.status_code == 200
    data = r.get_json()
    assert data["deleted"] == 0
    assert mp3.exists()


# ------------------------------------------------------------------
# P7 — settings/save accepts new fields
# ------------------------------------------------------------------

def test_settings_save_accepts_auto_delete(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "setup_complete": True})
    r = flask_client.post(
        "/settings/save",
        data=json.dumps({"auto_delete_recordings": True, "max_recordings_gb": 3.0}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    saved = cfg.load()
    assert saved["auto_delete_recordings"] is True
    assert saved["max_recordings_gb"] == 3.0


def test_settings_save_accepts_check_updates(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "setup_complete": True})
    r = flask_client.post(
        "/settings/save",
        data=json.dumps({"check_updates": False}),
        content_type="application/json",
    )
    assert r.status_code == 200
    assert cfg.load()["check_updates"] is False


# ------------------------------------------------------------------
# P7 — test-llm-stored
# ------------------------------------------------------------------

def test_test_llm_stored_no_key_returns_false(flask_client, monkeypatch):
    with patch("app.llm.anthropic_provider._get_api_key", return_value=""):
        r = flask_client.post(
            "/api/test-llm-stored",
            data=json.dumps({"provider": "anthropic"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is False
    assert "key" in data["error"].lower() or "klíč" in data["error"].lower()


# ------------------------------------------------------------------
# P7 — update-check
# ------------------------------------------------------------------

def test_update_check_mocked_response(flask_client, tmp_path, monkeypatch):
    import io
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "setup_complete": True})

    fake_release = json.dumps({"tag_name": "v9.9.9", "html_url": "https://github.com/kjarkovska/note-taker/releases/tag/v9.9.9"}).encode()

    class _FakeResp:
        def read(self): return fake_release
        def __enter__(self): return self
        def __exit__(self, *a): pass

    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        r = flask_client.post("/update-check")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["update_available"] is True
    assert data["version"] == "9.9.9"


def test_update_check_no_update_available(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    from app.version import VERSION
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "setup_complete": True})

    fake_release = json.dumps({"tag_name": f"v{VERSION}", "html_url": "https://github.com/"}).encode()

    class _FakeResp:
        def read(self): return fake_release
        def __enter__(self): return self
        def __exit__(self, *a): pass

    with patch("urllib.request.urlopen", return_value=_FakeResp()):
        r = flask_client.post("/update-check")
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["update_available"] is False


def test_update_check_network_error_returns_500(flask_client):
    with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
        r = flask_client.post("/update-check")
    assert r.status_code == 500
    assert r.get_json()["ok"] is False


def test_test_llm_stored_unknown_provider_returns_400(flask_client):
    r = flask_client.post(
        "/api/test-llm-stored",
        data=json.dumps({"provider": "unknown"}),
        content_type="application/json",
    )
    assert r.status_code == 400


def test_test_llm_stored_success_returns_ok_true(flask_client):
    with patch("app.llm.anthropic_provider._get_api_key", return_value="sk-stored"), \
         patch("app.llm.anthropic_provider.test_connection", return_value=None):
        r = flask_client.post(
            "/api/test-llm-stored",
            data=json.dumps({"provider": "anthropic"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_test_llm_stored_auth_error_returns_ok_false(flask_client):
    from app.exceptions import LLMAuthError
    with patch("app.llm.anthropic_provider._get_api_key", return_value="sk-bad"), \
         patch("app.llm.anthropic_provider.test_connection", side_effect=LLMAuthError("bad key")):
        r = flask_client.post(
            "/api/test-llm-stored",
            data=json.dumps({"provider": "anthropic"}),
            content_type="application/json",
        )
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is False
    assert "bad key" in data["error"]


def test_recordings_cleanup_deletes_error_job_files(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    rdir = tmp_path / "recordings"
    rdir.mkdir()
    mp3 = rdir / "error_job.mp3"
    mp3.write_bytes(b"audio")
    job_id = q.create_job(label="errored")
    q.update_job(job_id, audio_path=str(mp3))
    q.set_status(job_id, "queued")
    q.update_job(job_id, status="error")
    r = flask_client.post("/recordings/cleanup")
    assert r.status_code == 200
    assert r.get_json()["deleted"] == 1
    assert not mp3.exists()


def test_recordings_cleanup_deletes_orphaned_files(flask_client, tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "DATA_DIR", str(tmp_path))
    rdir = tmp_path / "recordings"
    rdir.mkdir()
    mp3 = rdir / "orphan.mp3"
    mp3.write_bytes(b"audio")
    # No job created — file is orphaned
    r = flask_client.post("/recordings/cleanup")
    assert r.status_code == 200
    assert r.get_json()["deleted"] == 1
    assert not mp3.exists()
