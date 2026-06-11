from unittest.mock import MagicMock, patch
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
    # A re-queue (status back to "queued") must have happened.
    assert any(
        c.kwargs.get("status") == "queued" or (c.args[1:] and "queued" in str(c))
        for c in update_calls
    )
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


def test_meeting_date_passes_to_generate_notes(mocks):
    job = _make_job({"transcript": "text", "meeting_date": "2025-05-22"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job

    Worker()._process_next()

    _, generate_kwargs = mocks["generate"].call_args
    assert generate_kwargs.get("date_str") == "2025-05-22"


def test_generate_notes_receives_language_from_config(mocks):
    job = _make_job({"transcript": "text"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job
    mocks["cfg"].load.return_value = {"vault_path": "/vault", "language_name": "German"}

    w = Worker()
    w._process_next()

    _, generate_kwargs = mocks["generate"].call_args
    assert generate_kwargs.get("language") == "German"


def test_glossary_terms_stored_in_glossary_terms_column(mocks):
    job = _make_job({"transcript": "text"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job
    mocks["suggest"].return_value = [{"canonical": "JIRA", "type": "product", "aliases": [], "context": "Issue tracker"}]

    w = Worker()
    w._process_next()

    update_calls = mocks["q"].update_job.call_args_list
    glossary_calls = [c for c in update_calls if "glossary_terms" in c.kwargs]
    assert len(glossary_calls) == 1
    assert "error_message" not in glossary_calls[0].kwargs


def test_llm_rate_limit_error_causes_retry(mocks):
    from app.exceptions import LLMRateLimitError

    job = _make_job({"transcript": "text"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job
    mocks["generate"].side_effect = LLMRateLimitError("rate limit hit")

    w = Worker()
    w._process_next()

    statuses = [c.kwargs.get("status") for c in mocks["q"].update_job.call_args_list if "status" in c.kwargs]
    assert "queued" in statuses


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


# ------------------------------------------------------------------
# Tray callbacks
# ------------------------------------------------------------------

def test_on_tooltip_called_after_done(mocks):
    tooltip = MagicMock()
    w = Worker()
    w.on_tooltip = tooltip
    w._process_next()
    tooltip.assert_called_with("ObsiNote")


def test_on_tooltip_called_on_model_not_ready(mocks):
    from app.exceptions import ModelNotReadyError
    mocks["transcribe"].side_effect = ModelNotReadyError("model missing")
    tooltip = MagicMock()
    w = Worker()
    w.on_tooltip = tooltip
    w._process_next()
    tooltip.assert_called_with("ObsiNote")


def test_on_tooltip_called_on_transcription_error(mocks):
    mocks["transcribe"].side_effect = RuntimeError("audio corrupted")
    tooltip = MagicMock()
    w = Worker()
    w.on_tooltip = tooltip
    w._process_next()
    tooltip.assert_called_with("ObsiNote")


def test_on_transcribing_callbacks_fired(mocks):
    on_transcribing = MagicMock()
    w = Worker()
    w.on_transcribing = on_transcribing
    w._process_next()
    on_transcribing.assert_any_call(True)
    on_transcribing.assert_any_call(False)


def test_on_transcribing_false_called_even_on_error(mocks):
    mocks["transcribe"].side_effect = RuntimeError("crash")
    on_transcribing = MagicMock()
    w = Worker()
    w.on_transcribing = on_transcribing
    w._process_next()
    on_transcribing.assert_any_call(False)


# ------------------------------------------------------------------
# Generation non-retryable exception
# ------------------------------------------------------------------

def test_generate_non_retryable_exception_marks_error(mocks):
    mocks["generate"].side_effect = RuntimeError("unexpected failure")
    w = Worker()
    w._process_next()
    update_calls = mocks["q"].update_job.call_args_list
    error_calls = [c for c in update_calls if c.kwargs.get("status") == "error"]
    assert len(error_calls) >= 1
    assert any("Generation failed" in str(c.kwargs.get("error_message", ""))
               for c in error_calls)


# ------------------------------------------------------------------
# vault_path not set
# ------------------------------------------------------------------

def test_vault_path_not_set_causes_retry(mocks):
    job = _make_job({"transcript": "text"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job
    mocks["cfg"].load.return_value = {"vault_path": "", "language_name": "Czech"}

    w = Worker()
    w._process_next()

    statuses = [c.kwargs.get("status") for c in mocks["q"].update_job.call_args_list
                if "status" in c.kwargs]
    assert "queued" in statuses


# ------------------------------------------------------------------
# Job with no audio path
# ------------------------------------------------------------------

def test_no_audio_path_marks_job_error(mocks):
    job = _make_job({"audio_path": None, "recording_path": None})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = _make_job({"transcript": "result"})

    w = Worker()
    w._process_next()

    update_calls = mocks["q"].update_job.call_args_list
    error_calls = [c for c in update_calls if c.kwargs.get("status") == "error"]
    assert len(error_calls) >= 1


# ------------------------------------------------------------------
# Glossary suggestion non-fatal
# ------------------------------------------------------------------

def test_glossary_suggestion_error_is_nonfatal(mocks):
    job = _make_job({"transcript": "text"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job
    mocks["suggest"].side_effect = RuntimeError("api down")

    w = Worker()
    w._process_next()

    mocks["q"].set_status.assert_any_call("test-job-id", "done")


# ------------------------------------------------------------------
# P8 — Recordings housekeeping
# ------------------------------------------------------------------

def test_auto_delete_removes_file_when_enabled(mocks, tmp_path):
    audio = tmp_path / "rec.mp3"
    audio.write_bytes(b"audio")
    job = _make_job({"transcript": "text", "keep_audio": None, "audio_path": str(audio)})
    done_job = {**job}
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.side_effect = [
        {**job, "transcript": "Hello world"},  # re-fetch after transcription
        done_job,                               # re-fetch in _maybe_delete_recording
    ]
    mocks["cfg"].load.return_value = {
        "vault_path": "/vault",
        "language_name": "Czech",
        "auto_delete_recordings": True,
        "max_recordings_gb": 0,
    }

    w = Worker()
    w._process_next()

    assert not audio.exists()
    update_calls = mocks["q"].update_job.call_args_list
    assert any(c.kwargs.get("audio_path") is None for c in update_calls)


def test_auto_delete_skips_when_keep_audio_set(mocks, tmp_path):
    audio = tmp_path / "rec.mp3"
    audio.write_bytes(b"audio")
    job = _make_job({"transcript": "text", "keep_audio": 1, "audio_path": str(audio)})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job
    mocks["cfg"].load.return_value = {
        "vault_path": "/vault",
        "language_name": "Czech",
        "auto_delete_recordings": True,
        "max_recordings_gb": 0,
    }

    w = Worker()
    w._process_next()

    assert audio.exists()


def test_auto_delete_skips_when_flag_off(mocks, tmp_path):
    audio = tmp_path / "rec.mp3"
    audio.write_bytes(b"audio")
    job = _make_job({"transcript": "text", "keep_audio": None, "audio_path": str(audio)})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job
    mocks["cfg"].load.return_value = {
        "vault_path": "/vault",
        "language_name": "Czech",
        "auto_delete_recordings": False,
        "max_recordings_gb": 0,
    }

    w = Worker()
    w._process_next()

    assert audio.exists()


def test_auto_delete_missing_file_no_crash(mocks):
    job = _make_job({"transcript": "text", "keep_audio": None, "audio_path": "/nonexistent/rec.mp3"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job
    mocks["cfg"].load.return_value = {
        "vault_path": "/vault",
        "language_name": "Czech",
        "auto_delete_recordings": True,
        "max_recordings_gb": 0,
    }

    w = Worker()
    w._process_next()  # should not raise

    mocks["q"].set_status.assert_any_call("test-job-id", "done")


def test_enforce_size_limit_deletes_oldest(monkeypatch, tmp_path):
    from app.worker import _enforce_size_limit
    import app.queue as q_real
    import app.config as cfg_real

    rdir = tmp_path / "recordings"
    rdir.mkdir()
    old_mp3 = rdir / "old.mp3"
    new_mp3 = rdir / "new.mp3"
    old_mp3.write_bytes(b"x" * 1024)
    new_mp3.write_bytes(b"x" * 1024)

    monkeypatch.setattr(q_real, "DB_PATH", str(tmp_path / "jobs.db"))
    q_real.init_db()
    monkeypatch.setattr(cfg_real, "DATA_DIR", str(tmp_path))

    j1 = q_real.create_job(label="old")
    q_real.update_job(j1, audio_path=str(old_mp3))
    q_real.update_job(j1, status="done", created_at="2026-01-01T10:00:00+00:00")

    j2 = q_real.create_job(label="new")
    q_real.update_job(j2, audio_path=str(new_mp3))
    q_real.update_job(j2, status="done", created_at="2026-01-02T10:00:00+00:00")

    # Limit smaller than total (2 KB), so oldest should be deleted
    _enforce_size_limit({"max_recordings_gb": 1 / (1024 ** 2), "auto_delete_recordings": False})

    assert not old_mp3.exists()
    assert new_mp3.exists()


# ------------------------------------------------------------------
# Worker thread lifecycle — start() / stop() / _loop()
# ------------------------------------------------------------------

def test_worker_start_creates_running_thread():
    w = Worker()
    with patch('app.worker.POLL_INTERVAL', 0), \
         patch.object(w, '_process_next'):
        w.start()
        assert w._thread is not None
        assert w._thread.is_alive()
        w.stop()


def test_worker_stop_terminates_thread():
    w = Worker()
    with patch('app.worker.POLL_INTERVAL', 0), \
         patch.object(w, '_process_next'):
        w.start()
        w.stop()
        assert not w._thread.is_alive()


def test_loop_swallows_process_next_exception_and_continues():
    """_loop() must catch any exception from _process_next() and keep running."""
    calls = []

    w = Worker()

    def fake_process_next():
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("unexpected crash")
        w._stop_event.set()  # exit after second successful call

    with patch('app.worker.POLL_INTERVAL', 0), \
         patch.object(w, '_process_next', side_effect=fake_process_next):
        w._loop()

    assert len(calls) == 2


# ------------------------------------------------------------------
# P8 — OSError swallowing in auto-delete paths
# ------------------------------------------------------------------

def test_auto_delete_oserror_is_swallowed(mocks, tmp_path):
    """An OSError during file removal must not propagate out of _process_next()."""
    audio = tmp_path / "rec.mp3"
    audio.write_bytes(b"audio")
    job = _make_job({"transcript": "text", "keep_audio": None, "audio_path": str(audio)})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.side_effect = [
        {**job, "transcript": "text"},
        job,
    ]
    mocks["cfg"].load.return_value = {
        "vault_path": "/vault",
        "language_name": "Czech",
        "auto_delete_recordings": True,
        "max_recordings_gb": 0,
    }

    with patch("app.worker.os.remove", side_effect=OSError("file locked")):
        w = Worker()
        w._process_next()  # must not raise

    mocks["q"].set_status.assert_any_call("test-job-id", "done")


def test_enforce_size_limit_oserror_is_swallowed(monkeypatch, tmp_path):
    """An OSError during deletion in _enforce_size_limit() must not propagate."""
    from app.worker import _enforce_size_limit
    import app.queue as q_real
    import app.config as cfg_real

    rdir = tmp_path / "recordings"
    rdir.mkdir()
    mp3 = rdir / "file.mp3"
    mp3.write_bytes(b"x" * 2048)

    monkeypatch.setattr(q_real, "DB_PATH", str(tmp_path / "jobs.db"))
    q_real.init_db()
    monkeypatch.setattr(cfg_real, "DATA_DIR", str(tmp_path))

    j = q_real.create_job(label="test")
    q_real.update_job(j, audio_path=str(mp3))
    q_real.update_job(j, status="done")

    with patch("app.worker.os.remove", side_effect=OSError("access denied")):
        _enforce_size_limit({"max_recordings_gb": 1 / (1024 ** 3)})  # limit of ~1 byte

    assert mp3.exists()  # file untouched because deletion was blocked


# ------------------------------------------------------------------
# Config injection
# ------------------------------------------------------------------

def test_worker_default_config_loader_uses_cfg_load():
    import app.config as real_cfg
    w = Worker()
    assert w._config_loader is real_cfg.load


def test_worker_injected_config_vault_path_empty_causes_retry(mocks):
    job = _make_job({"transcript": "text"})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.return_value = job

    w = Worker(config_loader=lambda: {"vault_path": "", "language_name": "Czech",
                                       "auto_delete_recordings": False, "max_recordings_gb": 0})
    w._process_next()

    statuses = [c.kwargs.get("status") for c in mocks["q"].update_job.call_args_list
                if "status" in c.kwargs]
    assert "queued" in statuses


def test_worker_injected_config_auto_delete_removes_file(mocks, tmp_path):
    audio = tmp_path / "rec.mp3"
    audio.write_bytes(b"audio")
    job = _make_job({"transcript": "text", "keep_audio": None, "audio_path": str(audio)})
    mocks["q"].list_jobs.return_value = [job]
    mocks["q"].get_job.side_effect = [
        {**job, "transcript": "Hello world"},
        {**job},
    ]

    w = Worker(config_loader=lambda: {"vault_path": "/vault", "language_name": "Czech",
                                       "auto_delete_recordings": True, "max_recordings_gb": 0})
    w._process_next()

    assert not audio.exists()


# ------------------------------------------------------------------
# Two-track parallel processing (P10)
# ------------------------------------------------------------------

def test_audio_track_calls_list_jobs_without_transcript(mocks):
    mocks["q"].list_jobs.return_value = []
    w = Worker()
    w._process_next()
    mocks["q"].list_jobs.assert_called_once_with(status="queued", has_transcript=False)


def test_import_track_calls_list_jobs_with_transcript(mocks):
    mocks["q"].list_jobs.return_value = []
    w = Worker()
    w._process_next(audio_track=False)
    mocks["q"].list_jobs.assert_called_once_with(status="queued", has_transcript=True)


def test_import_track_calls_generate_but_not_transcribe(mocks):
    imported_job = _make_job({"transcript": "Pre-existing transcript"})
    mocks["q"].list_jobs.return_value = [imported_job]
    mocks["q"].get_job.return_value = imported_job

    w = Worker()
    w._process_next(audio_track=False)

    mocks["transcribe"].assert_not_called()
    mocks["generate"].assert_called_once()
    mocks["q"].set_status.assert_any_call("test-job-id", "done")


def test_start_creates_exactly_two_threads():
    w = Worker()
    with patch('app.worker.POLL_INTERVAL', 0), \
         patch.object(w, '_process_next'):
        w.start()
        assert w._audio_thread is not None
        assert w._import_thread is not None
        assert w._audio_thread.is_alive()
        assert w._import_thread.is_alive()
        assert w._audio_thread is not w._import_thread
        w.stop()


def test_stop_joins_both_threads():
    w = Worker()
    with patch('app.worker.POLL_INTERVAL', 0), \
         patch.object(w, '_process_next'):
        w.start()
        w.stop()
        assert not w._audio_thread.is_alive()
        assert not w._import_thread.is_alive()


def test_thread_backward_compat_alias():
    w = Worker()
    with patch('app.worker.POLL_INTERVAL', 0), \
         patch.object(w, '_process_next'):
        w.start()
        assert w._thread is w._audio_thread
        w.stop()


def test_import_loop_swallows_exception_and_continues():
    calls = []
    w = Worker()

    def fake_process_next(audio_track=True):
        calls.append(audio_track)
        if len(calls) == 1:
            raise RuntimeError("crash")
        w._stop_event.set()

    with patch('app.worker.POLL_INTERVAL', 0), \
         patch.object(w, '_process_next', side_effect=fake_process_next):
        w._import_loop()

    assert len(calls) == 2
    assert all(t is False for t in calls)
