"""
queue.py — SQLite job queue for ObsiNote

State machine:
  recording → queued → transcribing → generating → done
                                                  ↘ error

Jobs are persisted to jobs.db so they survive app restarts.
On startup, any job stuck in 'transcribing' or 'generating' is reset to
'queued' so the worker picks it up again.

CLI usage (Phase 2 test):
  python app/queue.py --test
"""

import argparse
import logging
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from app.config import DATA_DIR
DB_PATH = os.path.join(DATA_DIR, "jobs.db")

STATES = ["recording", "queued", "transcribing", "generating", "done", "error"]

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    created_at       TEXT NOT NULL,
    label            TEXT,
    folder           TEXT,
    template         TEXT,
    meeting_date     TEXT,
    recording_path   TEXT,
    audio_path       TEXT,
    scratch_notes    TEXT,
    extra_context    TEXT,
    status           TEXT NOT NULL,
    transcript       TEXT,
    output_note_path TEXT,
    transcript_path  TEXT,
    keep_audio       INTEGER,
    error_message    TEXT,
    updated_at       TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ------------------------------------------------------------------
# Schema init
# ------------------------------------------------------------------

def init_db():
    """Create the jobs table if it doesn't exist, and apply any pending column migrations."""
    with _conn() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.execute(CREATE_TABLE)
        existing_cols = {row[1] for row in con.execute("PRAGMA table_info(jobs)").fetchall()}
        migrations = [
            ("transcript_path", "ALTER TABLE jobs ADD COLUMN transcript_path TEXT"),
            ("template",        "ALTER TABLE jobs ADD COLUMN template TEXT"),
            ("meeting_date",    "ALTER TABLE jobs ADD COLUMN meeting_date TEXT"),
            ("glossary_terms",  "ALTER TABLE jobs ADD COLUMN glossary_terms TEXT"),
            ("keep_audio",      "ALTER TABLE jobs ADD COLUMN keep_audio INTEGER"),
        ]
        for col, sql in migrations:
            if col not in existing_cols:
                con.execute(sql)
                logger.info("Migrated jobs table: added %s column", col)


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

def create_job(label="", folder=""):
    """Insert a new job in 'recording' state. Returns the job id."""
    job_id = str(uuid.uuid4())
    now = _now()
    with _conn() as con:
        con.execute(
            """
            INSERT INTO jobs
              (id, created_at, label, folder, status, updated_at)
            VALUES (?, ?, ?, ?, 'recording', ?)
            """,
            (job_id, now, label, folder, now),
        )
    return job_id


def get_job(job_id):
    """Return a job as a dict, or None if not found."""
    with _conn() as con:
        row = con.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(status: str | None = None, has_transcript: bool | None = None) -> list:
    """Return all jobs, optionally filtered by status and/or transcript presence, newest first."""
    conditions, params = [], []
    if status:
        conditions.append("status = ?")
        params.append(status)
    if has_transcript is True:
        conditions.append("transcript IS NOT NULL AND transcript != ''")
    elif has_transcript is False:
        conditions.append("(transcript IS NULL OR transcript = '')")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM jobs {where} ORDER BY created_at DESC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def update_job(job_id, **fields):
    """Update arbitrary fields on a job. Always updates updated_at."""
    if not fields:
        return
    fields["updated_at"] = _now()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [job_id]
    with _conn() as con:
        con.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)


def set_status(job_id, status):
    """Transition a job to a new status."""
    if status not in STATES:
        raise ValueError(f"Invalid status '{status}'. Must be one of: {STATES}")
    update_job(job_id, status=status)


def delete_job(job_id):
    with _conn() as con:
        con.execute("DELETE FROM jobs WHERE id = ? AND status IN ('done', 'error')", (job_id,))


def clear_completed():
    with _conn() as con:
        con.execute("DELETE FROM jobs WHERE status IN ('done', 'error')")


# ------------------------------------------------------------------
# Startup recovery
# ------------------------------------------------------------------

def recover_interrupted_jobs():
    """
    Reset jobs stuck mid-processing back to 'queued' so the worker retries them.
    Called once on app startup.
    """
    with _conn() as con:
        result = con.execute(
            """
            UPDATE jobs
               SET status = 'queued', updated_at = ?
             WHERE status IN ('transcribing', 'generating')
            """,
            (_now(),),
        )
    count = result.rowcount
    if count:
        logger.info("Recovered %d interrupted job(s) -> queued", count)
    return count


# ------------------------------------------------------------------
# CLI test
# ------------------------------------------------------------------

def _run_test():
    print("=== Phase 2 queue test ===\n")
    init_db()
    print(f"DB: {DB_PATH}")

    # Create a job
    job_id = create_job(label="Test meeting", folder="Other")
    print(f"Created job: {job_id}")

    job = get_job(job_id)
    assert job["status"] == "recording", f"Expected 'recording', got {job['status']}"
    print(f"  status: {job['status']} OK")

    # Walk through the state machine
    for state in ["queued", "transcribing", "generating", "done"]:
        time.sleep(0.05)
        set_status(job_id, state)
        job = get_job(job_id)
        assert job["status"] == state, f"Expected '{state}', got {job['status']}"
        print(f"  -> {state} OK")

    # Update some fields
    update_job(job_id, transcript="Ahoj světe.", output_note_path="/vault/test.md")
    job = get_job(job_id)
    assert job["transcript"] == "Ahoj světe."
    assert job["output_note_path"] == "/vault/test.md"
    print("  fields updated OK")

    # List
    jobs = list_jobs()
    assert any(j["id"] == job_id for j in jobs)
    print(f"  list_jobs() returned {len(jobs)} job(s) OK")

    # Recovery test — simulate a job stuck in transcribing
    stuck_id = create_job(label="Stuck job")
    set_status(stuck_id, "transcribing")
    print(f"\nSimulating interrupted job: {stuck_id} (transcribing)")
    recovered = recover_interrupted_jobs()
    assert recovered >= 1
    stuck = get_job(stuck_id)
    assert stuck["status"] == "queued", f"Expected 'queued', got {stuck['status']}"
    print(f"  recovered -> queued OK")

    # Clean up test jobs
    delete_job(job_id)
    delete_job(stuck_id)
    print("\nTest jobs deleted.")
    print("\n=== All tests passed ===")
    print("\nRestart this script to verify the DB file persists between runs.")


def main():
    parser = argparse.ArgumentParser(description="ObsiNote job queue — Phase 2 test")
    parser.add_argument("--test", action="store_true", help="Run the queue test")
    args = parser.parse_args()

    if args.test:
        _run_test()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
