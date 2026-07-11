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
