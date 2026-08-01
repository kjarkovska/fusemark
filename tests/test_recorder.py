import os
import wave
from unittest.mock import MagicMock, patch

import pytest

from app.recorder import (
    Recorder,
    list_partial_sessions,
    partial_paths,
    rewrite_wav_header,
    salvage_partial,
)


def _make_pa_mock(mic_open_raises=False):
    """A PyAudio mock with one loopback-flagged output device and one mic,
    so Recorder.start() can run its device-lookup logic without real hardware."""
    pa = MagicMock()
    pa.get_host_api_info_by_type.return_value = {"defaultOutputDevice": 0}
    pa.get_device_info_by_index.return_value = {
        "name": "Speakers (loopback)",
        "index": 0,
        "isLoopbackDevice": True,
        "defaultSampleRate": 48000.0,
        "maxInputChannels": 2,
    }
    pa.get_default_input_device_info.return_value = {
        "name": "Mic",
        "index": 1,
        "defaultSampleRate": 16000.0,
    }

    system_stream = MagicMock()
    if mic_open_raises:
        pa.open.side_effect = [system_stream, RuntimeError("mic busy")]
    else:
        pa.open.side_effect = [system_stream, MagicMock()]
    return pa, system_stream


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Recorder.start() now writes real partial WAV files under
    DATA_DIR/recordings/.partial/ — every test in this file must be pointed
    at a tmp_path, never the real %APPDATA%\\FuseMark."""
    monkeypatch.setattr("app.config.DATA_DIR", str(tmp_path))
    return tmp_path


def test_start_cleans_up_when_mic_open_fails(monkeypatch, tmp_path):
    pa, system_stream = _make_pa_mock(mic_open_raises=True)
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder(session_id="job-abc")
    with pytest.raises(RuntimeError, match="mic busy"):
        rec.start()

    # The already-opened loopback stream must be closed, not leaked.
    system_stream.stop_stream.assert_called_once()
    system_stream.close.assert_called_once()
    pa.terminate.assert_called_once()
    assert rec._pa is None
    assert rec._system_stream is None

    # And the partial WAVs opened before the failure must not be left behind.
    system_path, mic_path = partial_paths("job-abc")
    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)
    assert rec._system_wav_path is None
    assert rec._mic_wav_path is None


def test_start_succeeds_with_both_streams(monkeypatch):
    pa, system_stream = _make_pa_mock(mic_open_raises=False)
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder()
    rec.start()

    assert rec._pa is pa
    system_stream.start_stream.assert_called_once()
    rec.stop()


def test_start_opens_wav_files_with_stream_params(monkeypatch):
    pa, _ = _make_pa_mock()
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder(session_id="job-params")
    rec.start()
    system_path, mic_path = rec._system_wav_path, rec._mic_wav_path
    rec.stop()

    with wave.open(system_path, "rb") as wf:
        assert wf.getnchannels() == 2
        assert wf.getframerate() == 48000
        assert wf.getsampwidth() == 2
    with wave.open(mic_path, "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 16000


def test_callbacks_write_to_disk(monkeypatch):
    pa, _ = _make_pa_mock()
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder()
    rec.start()

    chunk = b"\x00\x01" * 100  # 100 int16 samples per channel-frame, arbitrary
    for _ in range(5):
        rec._system_callback(chunk, 100, {}, 0)
        rec._mic_callback(chunk, 100, {}, 0)

    system_path, mic_path = rec._system_wav_path, rec._mic_wav_path
    rec.stop()

    with wave.open(system_path, "rb") as wf:
        assert wf.getnframes() > 0
    with wave.open(mic_path, "rb") as wf:
        assert wf.getnframes() > 0


def test_recorder_keeps_no_frame_lists():
    rec = Recorder()
    assert not hasattr(rec, "_system_frames")
    assert not hasattr(rec, "_mic_frames")


def test_stop_is_idempotent(monkeypatch):
    pa, _ = _make_pa_mock()
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder()
    rec.start()
    rec.stop()
    rec.stop()  # must not raise

    assert rec._system_wav is None
    assert rec._mic_wav is None


def test_callback_after_stop_is_noop(monkeypatch):
    pa, _ = _make_pa_mock()
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder()
    rec.start()
    rec.stop()

    # A callback firing after stop() (a straggler from PortAudio's own
    # thread) must not raise, even though the WAV handle is now None.
    rec._system_callback(b"\x00\x01", 1, {}, 0)


def test_discard_is_idempotent(monkeypatch):
    pa, _ = _make_pa_mock()
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder(session_id="job-discard")
    rec.start()
    system_path, mic_path = rec._system_wav_path, rec._mic_wav_path
    rec.discard()
    rec.discard()  # must not raise

    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)
    assert rec._system_wav_path is None
    assert rec._mic_wav_path is None


# ------------------------------------------------------------------
# save()
# ------------------------------------------------------------------

def _record_a_bit(rec):
    chunk = b"\x00\x01" * 100
    rec._system_callback(chunk, 100, {}, 0)
    rec._mic_callback(chunk, 100, {}, 0)


def test_save_raises_when_nothing_recorded(monkeypatch, tmp_path):
    pa, _ = _make_pa_mock()
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder(session_id="job-empty")
    rec.start()
    system_path, mic_path = rec._system_wav_path, rec._mic_wav_path
    rec.stop()

    with pytest.raises(RuntimeError, match="Nothing was recorded"):
        rec.save(str(tmp_path / "out.mp3"))

    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)


def test_save_invokes_ffmpeg_with_partial_wav_paths(monkeypatch, tmp_path):
    pa, _ = _make_pa_mock()
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder(session_id="job-save")
    rec.start()
    _record_a_bit(rec)
    system_path, mic_path = rec._system_wav_path, rec._mic_wav_path
    rec.stop()

    out_path = str(tmp_path / "out.mp3")
    mock_result = MagicMock(returncode=0, stderr="")
    with patch("app.recorder.subprocess.run", return_value=mock_result) as mock_run:
        result = rec.save(out_path)

    assert result == out_path
    args = mock_run.call_args[0][0]
    assert system_path in args
    assert mic_path in args
    assert "amix=inputs=2:duration=longest" in args
    assert "-ar" in args and "16000" in args
    assert "-ac" in args and "1" in args
    # Partial WAVs are cleaned up once ffmpeg has consumed them.
    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)


def test_save_unlinks_partials_when_ffmpeg_fails(monkeypatch, tmp_path):
    pa, _ = _make_pa_mock()
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder(session_id="job-ffmpeg-fail")
    rec.start()
    _record_a_bit(rec)
    system_path, mic_path = rec._system_wav_path, rec._mic_wav_path
    rec.stop()

    mock_result = MagicMock(returncode=1, stderr="boom")
    with patch("app.recorder.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            rec.save(str(tmp_path / "out.mp3"))

    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)


def test_save_calls_stop_first_if_still_open(monkeypatch, tmp_path):
    """save() is documented as post-stop, but must defensively stop() itself
    if handles are still open rather than trying to read a live WAV file."""
    pa, _ = _make_pa_mock()
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder(session_id="job-defensive-stop")
    rec.start()
    _record_a_bit(rec)
    # Deliberately do NOT call rec.stop() before save().

    mock_result = MagicMock(returncode=0, stderr="")
    with patch("app.recorder.subprocess.run", return_value=mock_result):
        rec.save(str(tmp_path / "out.mp3"))

    assert rec._system_wav is None
    assert rec._pa is None


# ------------------------------------------------------------------
# WAV header salvage
# ------------------------------------------------------------------

def _write_valid_wav(path, channels=1, rate=16000, n_frames=50):
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x01" * n_frames * channels)


def test_rewrite_wav_header_repairs_truncated_header(tmp_path):
    path = tmp_path / "crashed.wav"
    _write_valid_wav(path, n_frames=50)

    # Simulate a crash: zero out the RIFF/data size fields the way an
    # unclosed wave.Wave_write leaves them (header written once at open,
    # never patched), while the actual PCM bytes remain on disk.
    raw = bytearray(path.read_bytes())
    raw[4:8] = (0).to_bytes(4, "little")
    raw[40:44] = (0).to_bytes(4, "little")
    path.write_bytes(bytes(raw))

    assert rewrite_wav_header(str(path)) is True

    with wave.open(str(path), "rb") as wf:
        assert wf.getnframes() == 50


def test_rewrite_wav_header_returns_false_on_garbage(tmp_path):
    path = tmp_path / "not_a_wav.wav"
    path.write_bytes(b"not a real wav file at all")
    assert rewrite_wav_header(str(path)) is False


def test_rewrite_wav_header_returns_false_on_missing_file(tmp_path):
    assert rewrite_wav_header(str(tmp_path / "nope.wav")) is False


# ------------------------------------------------------------------
# salvage_partial() / list_partial_sessions()
# ------------------------------------------------------------------

def test_salvage_partial_returns_none_when_nothing_usable(tmp_path):
    assert salvage_partial("no-such-session", str(tmp_path / "out.mp3")) is None


def test_salvage_partial_mixes_both_when_present(tmp_path):
    system_path, mic_path = partial_paths("job-salvage")
    _write_valid_wav(system_path, channels=2, rate=48000, n_frames=50)
    _write_valid_wav(mic_path, channels=1, rate=16000, n_frames=50)

    out_path = str(tmp_path / "out.mp3")
    mock_result = MagicMock(returncode=0, stderr="")
    with patch("app.recorder.subprocess.run", return_value=mock_result) as mock_run:
        result = salvage_partial("job-salvage", out_path)

    assert result == out_path
    args = mock_run.call_args[0][0]
    assert system_path in args and mic_path in args
    assert "amix=inputs=2:duration=longest" in args
    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)


def test_salvage_partial_uses_single_stream_when_only_one_usable(tmp_path):
    system_path, mic_path = partial_paths("job-single")
    _write_valid_wav(system_path, channels=2, rate=48000, n_frames=50)
    # No mic file at all — only the system stream survived the crash.

    out_path = str(tmp_path / "out.mp3")
    mock_result = MagicMock(returncode=0, stderr="")
    with patch("app.recorder.subprocess.run", return_value=mock_result) as mock_run:
        result = salvage_partial("job-single", out_path)

    assert result == out_path
    args = mock_run.call_args[0][0]
    assert system_path in args
    assert "amix=inputs=2:duration=longest" not in args
    assert not os.path.exists(system_path)


def test_salvage_partial_returns_none_when_ffmpeg_fails(tmp_path):
    system_path, mic_path = partial_paths("job-salvage-fail")
    _write_valid_wav(system_path, n_frames=50)
    _write_valid_wav(mic_path, n_frames=50)

    mock_result = MagicMock(returncode=1, stderr="boom")
    with patch("app.recorder.subprocess.run", return_value=mock_result):
        result = salvage_partial("job-salvage-fail", str(tmp_path / "out.mp3"))

    assert result is None
    # Cleanup still happens even when ffmpeg fails.
    assert not os.path.exists(system_path)
    assert not os.path.exists(mic_path)


def test_list_partial_sessions_finds_sessions_by_system_file(tmp_path):
    system_path, mic_path = partial_paths("job-listed")
    _write_valid_wav(system_path, n_frames=10)
    _write_valid_wav(mic_path, n_frames=10)

    assert list_partial_sessions() == ["job-listed"]


def test_list_partial_sessions_empty_when_no_partial_dir(tmp_path):
    assert list_partial_sessions() == []
