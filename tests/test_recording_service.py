import os
from unittest.mock import MagicMock, patch

import pytest

import app.queue as q
from app.recording_service import RecordingService


@pytest.fixture(autouse=True)
def isolated_db(db_path):
    """Each test gets a fresh in-memory DB via the db_path fixture from conftest."""


@pytest.fixture
def service():
    return RecordingService()


@pytest.fixture
def service_with_tray():
    tray = MagicMock()
    svc = RecordingService(tray=tray)
    return svc, tray


# ------------------------------------------------------------------
# Initial state
# ------------------------------------------------------------------

def test_is_recording_false_initially(service):
    assert service.is_recording is False


def test_current_job_id_none_initially(service):
    assert service.current_job_id is None


def test_recorder_property_none_initially(service):
    assert service.recorder is None


def test_recorder_property_returns_recorder_while_recording(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    with patch("app.recorder.Recorder", return_value=mock_rec):
        service.start()

    assert service.recorder is mock_rec


def test_recorder_property_none_after_stop(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    with patch("app.recorder.Recorder", return_value=mock_rec):
        service.start()

    service.stop()

    assert service.recorder is None


# ------------------------------------------------------------------
# start()
# ------------------------------------------------------------------

def test_start_creates_job_in_queue(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    with patch("app.recorder.Recorder", return_value=mock_rec):
        result = service.start(label="Standup", folder="Other")

    assert "job_id" in result
    job = q.get_job(result["job_id"])
    assert job["label"] == "Standup"
    assert job["folder"] == "Other"


def test_start_starts_recorder(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    with patch("app.recorder.Recorder", return_value=mock_rec):
        service.start()

    mock_rec.start.assert_called_once()


def test_start_saves_template_on_job(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        result = service.start(label="x", template="Meeting")

    assert q.get_job(result["job_id"])["template"] == "Meeting"


def test_start_sets_is_recording_true(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        service.start()

    assert service.is_recording is True


def test_start_sets_current_job_id(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        result = service.start()

    assert service.current_job_id == result["job_id"]


def test_start_when_already_recording_returns_error(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        service.start()
        second = service.start()

    assert "error" in second


def test_start_when_recorder_start_raises_returns_error(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    mock_rec.start.side_effect = RuntimeError("mic busy")
    with patch("app.recorder.Recorder", return_value=mock_rec):
        result = service.start()

    assert "error" in result
    assert service.is_recording is False
    assert service.current_job_id is None


def test_start_notifies_tray(service_with_tray, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    svc, tray = service_with_tray
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        svc.start()

    tray.set_recording.assert_called_once_with(True)


# ------------------------------------------------------------------
# stop()
# ------------------------------------------------------------------

def test_stop_when_not_recording_returns_error(service):
    result = service.stop()
    assert "error" in result


def test_stop_saves_audio_and_queues_job(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    with patch("app.recorder.Recorder", return_value=mock_rec):
        start_result = service.start(label="Test")

    stop_result = service.stop()

    assert "audio_path" in stop_result
    assert stop_result["job_id"] == start_result["job_id"]
    job = q.get_job(start_result["job_id"])
    assert job["status"] == "queued"
    assert job["audio_path"].endswith(".mp3")
    mock_rec.save.assert_called_once()


def test_stop_clears_is_recording(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        service.start()

    service.stop()

    assert service.is_recording is False
    assert service.current_job_id is None


def test_stop_calls_tray_set_recording_false(service_with_tray, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    svc, tray = service_with_tray
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        svc.start()

    svc.stop()

    tray.set_recording.assert_called_with(False)


def test_start_fires_on_recording_callback(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    calls = []
    service.on_recording = calls.append
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        service.start()

    assert calls == [True]


def test_stop_fires_on_recording_callback_false(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    calls = []
    service.on_recording = calls.append
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        service.start()
    calls.clear()

    service.stop()

    assert calls == [False]


def test_on_recording_not_required(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    with patch("app.recorder.Recorder", return_value=MagicMock()):
        service.start()
    service.stop()  # no on_recording set — must not raise


def test_stop_when_save_raises_marks_job_error(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    mock_rec.save.side_effect = RuntimeError("Nothing was recorded.")
    with patch("app.recorder.Recorder", return_value=mock_rec):
        start_result = service.start(label="Test")

    result = service.stop()

    assert "error" in result
    job = q.get_job(start_result["job_id"])
    assert job["status"] == "error"
    assert "Nothing was recorded" in job["error_message"]


def test_stop_when_save_raises_still_clears_is_recording(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    mock_rec.save.side_effect = RuntimeError("boom")
    with patch("app.recorder.Recorder", return_value=mock_rec):
        service.start()

    service.stop()

    assert service.is_recording is False
    assert service.current_job_id is None


def test_stop_when_save_raises_still_notifies_tray(service_with_tray, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    svc, tray = service_with_tray
    mock_rec = MagicMock()
    mock_rec.save.side_effect = RuntimeError("boom")
    with patch("app.recorder.Recorder", return_value=mock_rec):
        svc.start()

    svc.stop()

    tray.set_recording.assert_called_with(False)


def test_stop_discards_recorder_when_save_fails(service, tmp_path, monkeypatch):
    """A crashed/failed save() leaves partial WAVs on disk — discard() must
    run to clean them up instead of just dropping the Recorder object."""
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    mock_rec.save.side_effect = RuntimeError("boom")
    with patch("app.recorder.Recorder", return_value=mock_rec):
        service.start()

    service.stop()

    mock_rec.discard.assert_called_once()


def test_stop_discards_recorder_when_stop_itself_raises(service, tmp_path, monkeypatch):
    """If r.stop() (not save()) is what fails, save() never runs and never
    gets a chance to clean up — discard() is the only thing that will."""
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    mock_rec.stop.side_effect = RuntimeError("stream teardown failed")
    with patch("app.recorder.Recorder", return_value=mock_rec):
        start_result = service.start(label="Test")

    result = service.stop()

    assert "error" in result
    mock_rec.discard.assert_called_once()
    job = q.get_job(start_result["job_id"])
    assert job["status"] == "error"


# ------------------------------------------------------------------
# start() — job created before the recorder, so the job id can name the
# partial WAV files (session_id) for crash recovery
# ------------------------------------------------------------------

def test_start_passes_job_id_as_session_id(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    captured = {}

    def _fake_recorder(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    with patch("app.recorder.Recorder", side_effect=_fake_recorder):
        result = service.start(label="Test")

    assert captured["session_id"] == result["job_id"]


def test_start_failure_marks_job_error(service, tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    mock_rec = MagicMock()
    mock_rec.start.side_effect = RuntimeError("mic busy")
    with patch("app.recorder.Recorder", return_value=mock_rec):
        result = service.start(label="Test")

    assert "error" in result
    # The job was created before r.start() so its id could be the session_id
    # — a failure must not leave that job stuck in 'recording' forever.
    jobs = q.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["status"] == "error"
    assert jobs[0]["label"] == "Test"
    assert "mic busy" in jobs[0]["error_message"]


# ------------------------------------------------------------------
# salvage_interrupted_recordings()
# ------------------------------------------------------------------

def _write_partial_wav(path, channels=1, rate=16000, n_frames=50):
    import os
    import wave
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x01" * n_frames * channels)


def test_salvage_recovers_ghost_recording_job(tmp_path, monkeypatch):
    from app.recorder import partial_paths
    from app.recording_service import salvage_interrupted_recordings

    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    job_id = q.create_job(label="crashed meeting")
    system_path, mic_path = partial_paths(job_id)
    _write_partial_wav(system_path, channels=2, rate=48000)
    _write_partial_wav(mic_path, channels=1, rate=16000)

    mock_result = MagicMock(returncode=0, stderr="")
    with patch("app.recorder.subprocess.run", return_value=mock_result):
        salvaged = salvage_interrupted_recordings()

    assert salvaged == 1
    job = q.get_job(job_id)
    assert job["status"] == "queued"
    assert job["audio_path"].endswith(f"{job_id}.mp3")
    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)


def test_salvage_sweeps_orphan_partial_with_no_job(tmp_path, monkeypatch):
    from app.recorder import partial_paths
    from app.recording_service import salvage_interrupted_recordings

    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    system_path, mic_path = partial_paths("no-such-job")
    _write_partial_wav(system_path)
    _write_partial_wav(mic_path)

    salvaged = salvage_interrupted_recordings()

    assert salvaged == 0
    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)


def test_salvage_sweeps_orphan_partial_for_job_not_recording(tmp_path, monkeypatch):
    """A partial left behind for a job that already moved on (e.g. a
    previous salvage attempt updated it to 'queued') must not be re-salvaged
    or mistaken for something still in progress."""
    from app.recorder import partial_paths
    from app.recording_service import salvage_interrupted_recordings

    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    job_id = q.create_job(label="already handled")
    q.set_status(job_id, "done")
    system_path, mic_path = partial_paths(job_id)
    _write_partial_wav(system_path)
    _write_partial_wav(mic_path)

    salvaged = salvage_interrupted_recordings()

    assert salvaged == 0
    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)


def test_salvage_returns_zero_when_nothing_to_salvage(tmp_path, monkeypatch):
    from app.recording_service import salvage_interrupted_recordings

    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    assert salvage_interrupted_recordings() == 0
