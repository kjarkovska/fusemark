"""
tests/test_integration.py — Worker + real SQLite integration tests

Mocks only external I/O (transcribe, generate_notes, save_note,
save_transcript, suggest_glossary_terms, cfg.load). Everything else
— SQLite schema, status transitions, field persistence — is real.

This catches bugs that unit tests miss: wrong field names passed to
update_job, status transition ordering, retry-count persistence across
the worker/queue boundary.
"""

import json
import time

import pytest
from unittest.mock import patch

import app.queue as q
from app.exceptions import LLMRateLimitError, ModelNotReadyError
from app.worker import MAX_RETRIES, Worker, _RetryableError

FAKE_AUDIO = "/fake/audio.mp3"
FAKE_VAULT = "/fake/vault"


@pytest.fixture
def w(db_path):
    """Worker wired to real SQLite; only external I/O is mocked."""
    with (
        patch("app.worker.transcribe") as mock_transcribe,
        patch("app.worker.generate_notes") as mock_generate,
        patch("app.worker.save_note") as mock_save_note,
        patch("app.worker.save_transcript") as mock_save_transcript,
        patch("app.worker.suggest_glossary_terms") as mock_suggest,
        patch("app.worker.cfg") as mock_cfg,
    ):
        mock_cfg.load.return_value = {"vault_path": FAKE_VAULT, "language_name": "Czech"}
        mock_transcribe.return_value = "Transcribed text"
        mock_generate.return_value = "# Note"
        mock_save_note.return_value = "/fake/vault/note.md"
        mock_save_transcript.return_value = "/fake/vault/transcript.md"
        mock_suggest.return_value = []

        worker = Worker()
        yield worker, {
            "transcribe": mock_transcribe,
            "generate": mock_generate,
            "save_note": mock_save_note,
            "save_transcript": mock_save_transcript,
            "suggest": mock_suggest,
            "cfg": mock_cfg,
        }


def _queued_job(label="Test", audio_path=FAKE_AUDIO, **fields):
    """Insert a real queued job into the DB and return its ID."""
    job_id = q.create_job(label=label)
    q.update_job(job_id, audio_path=audio_path, **fields)
    q.set_status(job_id, "queued")
    return job_id


# ------------------------------------------------------------------
# Happy path
# ------------------------------------------------------------------

def test_happy_path_status_reaches_done(w):
    worker, _ = w
    job_id = _queued_job()
    worker._process_next()
    assert q.get_job(job_id)["status"] == "done"


def test_happy_path_fields_persisted_in_db(w):
    worker, _ = w
    job_id = _queued_job()
    worker._process_next()
    job = q.get_job(job_id)
    assert job["transcript"] == "Transcribed text"
    assert job["output_note_path"] == "/fake/vault/note.md"
    assert job["transcript_path"] == "/fake/vault/transcript.md"


# ------------------------------------------------------------------
# Import job (transcript pre-populated)
# ------------------------------------------------------------------

def test_import_job_skips_transcription_and_reaches_done(w):
    worker, mocks = w
    job_id = _queued_job(audio_path=None, transcript="Pre-existing transcript")
    worker._process_next(audio_track=False)
    mocks["transcribe"].assert_not_called()
    assert q.get_job(job_id)["status"] == "done"


# ------------------------------------------------------------------
# Transcription errors
# ------------------------------------------------------------------

def test_transcription_error_persists_error_status_and_message(w):
    worker, mocks = w
    mocks["transcribe"].side_effect = RuntimeError("corrupted audio")
    job_id = _queued_job()
    worker._process_next()
    job = q.get_job(job_id)
    assert job["status"] == "error"
    assert "corrupted audio" in job["error_message"]


def test_model_not_ready_persists_clean_error_message(w):
    worker, mocks = w
    mocks["transcribe"].side_effect = ModelNotReadyError(
        "Whisper model not downloaded — go to Settings to download it."
    )
    job_id = _queued_job()
    worker._process_next()
    job = q.get_job(job_id)
    assert job["status"] == "error"
    assert "go to Settings" in job["error_message"]


# ------------------------------------------------------------------
# Retryable generation errors
# ------------------------------------------------------------------

def test_retryable_error_requeues_with_retry_count(w):
    worker, mocks = w
    mocks["generate"].side_effect = LLMRateLimitError("rate limit hit")
    job_id = _queued_job(transcript="some text")
    worker._process_next(audio_track=False)
    job = q.get_job(job_id)
    assert job["status"] == "queued"
    assert job["retry_count"] == 1
    assert job["error_message"] == "rate limit hit"


def test_max_retries_exceeded_marks_permanent_error(w):
    worker, mocks = w
    mocks["generate"].side_effect = _RetryableError("still failing")
    job_id = _queued_job(
        transcript="text",
        retry_count=MAX_RETRIES,
    )
    worker._process_next(audio_track=False)
    job = q.get_job(job_id)
    assert job["status"] == "error"
    assert f"after {MAX_RETRIES} retries" in job["error_message"]


# ------------------------------------------------------------------
# Vault path not configured
# ------------------------------------------------------------------

def test_vault_path_not_set_requeues_job(w):
    worker, mocks = w
    mocks["cfg"].load.return_value = {"vault_path": "", "language_name": "Czech"}
    job_id = _queued_job(transcript="text")
    worker._process_next(audio_track=False)
    assert q.get_job(job_id)["status"] == "queued"


# ------------------------------------------------------------------
# Glossary terms
# ------------------------------------------------------------------

def test_glossary_terms_persisted_as_json(w):
    worker, mocks = w
    terms = [{"canonical": "JIRA", "type": "product", "aliases": [], "context": "tracker"}]
    mocks["suggest"].return_value = terms
    job_id = _queued_job(transcript="text")
    worker._process_next(audio_track=False)
    job = q.get_job(job_id)
    assert job["glossary_terms"] is not None
    assert json.loads(job["glossary_terms"])[0]["canonical"] == "JIRA"


# ------------------------------------------------------------------
# FIFO ordering
# ------------------------------------------------------------------

def test_fifo_oldest_queued_job_processed_first(w):
    worker, _ = w
    job_id_first = _queued_job(label="First")
    time.sleep(0.01)  # ensure distinct created_at timestamps
    job_id_second = _queued_job(label="Second")
    worker._process_next()
    assert q.get_job(job_id_first)["status"] == "done"
    assert q.get_job(job_id_second)["status"] == "queued"
