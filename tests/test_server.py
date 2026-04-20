import json
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
