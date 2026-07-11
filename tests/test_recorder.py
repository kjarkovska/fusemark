from unittest.mock import MagicMock

import pytest

from app.recorder import Recorder


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


def test_start_cleans_up_when_mic_open_fails(monkeypatch):
    pa, system_stream = _make_pa_mock(mic_open_raises=True)
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder()
    with pytest.raises(RuntimeError, match="mic busy"):
        rec.start()

    # The already-opened loopback stream must be closed, not leaked.
    system_stream.stop_stream.assert_called_once()
    system_stream.close.assert_called_once()
    pa.terminate.assert_called_once()
    assert rec._pa is None
    assert rec._system_stream is None


def test_start_succeeds_with_both_streams(monkeypatch):
    pa, system_stream = _make_pa_mock(mic_open_raises=False)
    monkeypatch.setattr("app.recorder.pyaudio.PyAudio", lambda: pa)

    rec = Recorder()
    rec.start()

    assert rec._pa is pa
    system_stream.start_stream.assert_called_once()
