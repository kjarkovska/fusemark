from unittest.mock import MagicMock, call, patch
import pytest

from app.exceptions import ModelNotReadyError
from app.worker import Worker, _parse_retry_count, _RetryableError


def _make_job(overrides=None):
    base = {
        "id": "test-job-id",
        "label": "Test Meeting",
        "folder": "Other",
        "template": None,
        "meeting_date": None,
        "transcript": None,
        "scratch_notes": None,
        "extra_context": None,
        "audio_path": "/tmp/audio.mp3",
        "recording_path": None,
        "created_at": "2026-01-01T10:00:00+00:00",
        "error_message": None,
    }
    if overrides:
        base.update(overrides)
    return base


@pytest.fixture
def mocks():
    job = _make_job()
    job_with_transcript = _make_job({"transcript": "Hello world"})

    with (
        patch("app.worker.q") as mock_q,
        patch("app.worker.cfg") as mock_cfg,
        patch("app.worker.transcribe") as mock_transcribe,
        patch("app.worker.generate_notes") as mock_generate,
        patch("app.worker.save_note") as mock_save_note,
        patch("app.worker.save_transcript") as mock_save_transcript,
        patch("app.worker.suggest_glossary_terms") as mock_suggest,
    ):
        mock_cfg.load.return_value = {"vault_path": "/vault", "whisper_model": "small"}
        mock_q.list_jobs.return_value = [job]
        mock_q.get_job.return_value = job_with_transcript
        mock_transcribe.return_value = "Hello world"
        mock_generate.return_value = "# Note"
        mock_save_note.return_value = "/vault/note.md"
        mock_save_transcript.return_value = "/vault/transcript.md"
        mock_suggest.return_value = []

        yield {
            "q": mock_q,
            "cfg": mock_cfg,
            "transcribe": mock_transcribe,
            "generate": mock_generate,
            "save_note": mock_save_note,
            "save_transcript": mock_save_transcript,
            "suggest": mock_suggest,
            "job": job,
            "job_with_transcript": job_with_transcript,
        }


# ------------------------------------------------------------------
# _parse_retry_count()
# ------------------------------------------------------------------

def test_parse_retry_count_valid():
    assert _parse_retry_count("retry:3:Connection error") == 3


def test_parse_retry_count_zero():
    assert _parse_retry_count("retry:0:something") == 0


def test_parse_retry_count_empty():
    assert _parse_retry_count("") == 0


def test_parse_retry_count_none():
    assert _parse_retry_count(None) == 0


def test_parse_retry_count_unrelated_message():
    assert _parse_retry_count("Transcription failed: oops") == 0


def test_parse_retry_count_malformed():
    assert _parse_retry_count("retry:abc:msg") == 0


# ------------------------------------------------------------------
# Normal flow
# ------------------------------------------------------------------

def test_normal_flow(mocks):
    w = Worker()
    w._process_next()

    mocks["q"].set_status.assert_any_call("test-job-id", "transcribing")
    mocks["q"].set_status.assert_any_call("test-job-id", "generating")
    mocks["q"].set_status.assert_any_call("test-job-id", "done")
    mocks["transcribe"].assert_called_once()
    mocks["generate"].assert_called_once()
    mocks["save_note"].assert_called_once()
    mocks["save_transcript"].assert_called_once()


def test_normal_flow_refetches_job_after_transcription(mocks):
    w = Worker()
    w._process_next()
    mocks["q"].get_job.assert_called_with("test-job-id")


# ------------------------------------------------------------------
# Imported job (transcript pre-populated)
# ------------------------------------------------------------------

def test_imported_job_skips_transcription(mocks):
    imported_job = _make_job({"transcript": "Pre-existing transcript"})
    mocks["q"].list_jobs.return_value = [imported_job]
    mocks["q"].get_job.return_value = imported_job

    w = Worker()
    w._process_next()

    mocks["transcribe"].assert_not_called()
    mocks["generate"].assert_called_once()
    mocks["q"].set_status.assert_any_call("test-job-id", "done")


def test_imported_job_does_not_set_transcribing_status(mocks):
    imported_job = _make_job({"transcript": "Already transcribed"})
    mocks["q"].list_jobs.return_value = [imported_job]
    mocks["q"].get_job.return_value = imported_job

    w = Worker()
    w._process_next()

    called_statuses = [c.args[1] for c in mocks["q"].set_status.call_args_list]
    assert "transcribing" not in called_statuses


# ------------------------------------------------------------------
# Transcription error
# ------------------------------------------------------------------

def test_transcription_error_marks_job_error(mocks):
    mocks["transcribe"].side_effect = RuntimeError("audio corrupted")

    w = Worker()
    w._process_next()

    mocks["q"].update_job.assert_called_with(
        "test-job-id",
        status="error",
        error_message="Transcription failed: audio corrupted",
    )
    mocks["generate"].assert_not_called()


def test_model_not_ready_uses_clean_message(mocks):
    mocks["transcribe"].side_effect = ModelNotReadyError(
        "Whisper model not downloaded — go to Settings to download it."
    )

    w = Worker()
    w._process_next()

    mocks["q"].update_job.assert_called_with(
        "test-job-id",
        status="error",
        error_message="Whisper model not downloaded — go to Settings to download it.",
    )
    mocks["generate"].assert_not_called()


# ------------------------------------------------------------------
# Retryable generation error
# ------------------------------------------------------------------

def test_retryable_error_increments_retry_count(mocks):
    mocks["generate"].side_effect = _RetryableError("rate limit")

    w = Worker()
    w._process_next()

    update_calls = mocks["q"].update_job.call_args_list
    retry_call = next(c for c in update_calls if c.kwargs.get("status") == "queued" or
                      (c.args[1:] and "queued" in str(c)))
    # Check error_message starts with "retry:1:"
    error_msgs = [
        c.kwargs.get("error_message", "") or (c.args[2] if len(c.args) > 2 else "")
        for c in update_calls
    ]
    assert any(str(msg).startswith("retry:1:") for msg in error_msgs)


def test_retryable_error_requeues_job(mocks):
    mocks["generate"].side_effect = _RetryableError("connection error")

    w = Worker()
    w._process_next()

    statuses = [
        c.kwargs.get("status") for c in mocks["q"].update_job.call_args_list
        if "status" in c.kwargs
    ]
    assert "queued" in statuses


def test_max_retries_marks_permanent_error(mocks):
    # Use pre-populated transcript so worker doesn't re-fetch job (which would reset error_message)
    job = _make_job({"transcript": "text", "error_message": "retry:5:previous error"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["generate"].side_effect = _RetryableError("still failing")

    w = Worker()
    w._process_next()

    update_calls = mocks["q"].update_job.call_args_list
    error_statuses = [c for c in update_calls if c.kwargs.get("status") == "error"]
    assert len(error_statuses) >= 1


# ------------------------------------------------------------------
# Meeting date threading
# ------------------------------------------------------------------

def test_meeting_date_threads_to_save_functions(mocks):
    job = _make_job({"transcript": "text", "meeting_date": "2025-06-01"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job

    w = Worker()
    w._process_next()

    _, save_transcript_kwargs = mocks["save_transcript"].call_args
    assert save_transcript_kwargs.get("date_str") == "2025-06-01"

    _, save_note_kwargs = mocks["save_note"].call_args
    assert save_note_kwargs.get("date_str") == "2025-06-01"


def test_generate_notes_receives_date_str(mocks):
    job = _make_job({"transcript": "text", "meeting_date": "2025-11-20"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job

    w = Worker()
    w._process_next()

    _, generate_kwargs = mocks["generate"].call_args
    assert generate_kwargs.get("date_str") == "2025-11-20"


# ------------------------------------------------------------------
# Empty queue
# ------------------------------------------------------------------

def test_empty_queue_does_nothing(mocks):
    mocks["q"].list_jobs.return_value = []

    w = Worker()
    w._process_next()

    mocks["transcribe"].assert_not_called()
    mocks["generate"].assert_not_called()
    mocks["q"].set_status.assert_not_called()
