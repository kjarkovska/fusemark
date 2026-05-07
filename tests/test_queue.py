import pytest
import app.queue as q


def test_create_job_defaults(db_path):
    job_id = q.create_job(label="Test", folder="Other")
    job = q.get_job(job_id)
    assert job is not None
    assert job["status"] == "recording"
    assert job["label"] == "Test"
    assert job["folder"] == "Other"


def test_create_job_returns_uuid(db_path):
    job_id = q.create_job()
    assert len(job_id) == 36
    assert job_id.count("-") == 4


def test_set_status_valid(db_path):
    job_id = q.create_job()
    for status in ["queued", "transcribing", "generating", "done"]:
        q.set_status(job_id, status)
        assert q.get_job(job_id)["status"] == status


def test_set_status_invalid(db_path):
    job_id = q.create_job()
    with pytest.raises(ValueError, match="Invalid status"):
        q.set_status(job_id, "flying")


def test_delete_job_done(db_path):
    job_id = q.create_job()
    q.set_status(job_id, "queued")
    q.set_status(job_id, "done")
    q.delete_job(job_id)
    assert q.get_job(job_id) is None


def test_delete_job_error(db_path):
    job_id = q.create_job()
    q.set_status(job_id, "queued")
    q.set_status(job_id, "error")
    q.delete_job(job_id)
    assert q.get_job(job_id) is None


def test_delete_job_blocked_in_progress(db_path):
    job_id = q.create_job()
    q.set_status(job_id, "queued")
    q.delete_job(job_id)  # should be no-op
    assert q.get_job(job_id) is not None


def test_recover_interrupted(db_path):
    j1 = q.create_job(label="A")
    j2 = q.create_job(label="B")
    q.set_status(j1, "queued")
    q.set_status(j1, "transcribing")
    q.set_status(j2, "queued")
    q.set_status(j2, "generating")
    count = q.recover_interrupted_jobs()
    assert count == 2
    assert q.get_job(j1)["status"] == "queued"
    assert q.get_job(j2)["status"] == "queued"


def test_recover_skips_other_statuses(db_path):
    j_rec = q.create_job(label="recording")
    j_done = q.create_job(label="done")
    q.set_status(j_done, "queued")
    q.set_status(j_done, "done")
    j_err = q.create_job(label="error")
    q.set_status(j_err, "queued")
    q.set_status(j_err, "error")
    count = q.recover_interrupted_jobs()
    assert count == 0
    assert q.get_job(j_rec)["status"] == "recording"
    assert q.get_job(j_done)["status"] == "done"
    assert q.get_job(j_err)["status"] == "error"


def test_clear_completed(db_path):
    j_done = q.create_job()
    q.set_status(j_done, "queued")
    q.set_status(j_done, "done")
    j_err = q.create_job()
    q.set_status(j_err, "queued")
    q.set_status(j_err, "error")
    j_active = q.create_job()
    q.set_status(j_active, "queued")
    q.clear_completed()
    assert q.get_job(j_done) is None
    assert q.get_job(j_err) is None
    assert q.get_job(j_active) is not None


def test_list_jobs_filter(db_path):
    j1 = q.create_job()
    j2 = q.create_job()
    q.set_status(j1, "queued")
    q.set_status(j2, "queued")
    q.set_status(j2, "done")
    queued = q.list_jobs(status="queued")
    assert len(queued) == 1
    assert queued[0]["id"] == j1


def test_update_job_arbitrary_fields(db_path):
    job_id = q.create_job()
    q.update_job(job_id, transcript="hello", extra_context="ctx")
    job = q.get_job(job_id)
    assert job["transcript"] == "hello"
    assert job["extra_context"] == "ctx"


def test_get_job_missing(db_path):
    assert q.get_job("nonexistent-id") is None


def test_meeting_date_field(db_path):
    job_id = q.create_job()
    q.update_job(job_id, meeting_date="2025-06-01", template="Meeting")
    job = q.get_job(job_id)
    assert job["meeting_date"] == "2025-06-01"
    assert job["template"] == "Meeting"


def test_init_db_creates_glossary_terms_column(db_path):
    import sqlite3
    with sqlite3.connect(db_path) as con:
        cols = {row[1] for row in con.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "glossary_terms" in cols


def test_update_job_no_fields_is_noop(db_path):
    job_id = q.create_job()
    before = q.get_job(job_id)
    q.update_job(job_id)  # no fields — early return, updated_at unchanged
    after = q.get_job(job_id)
    assert before["updated_at"] == after["updated_at"]
