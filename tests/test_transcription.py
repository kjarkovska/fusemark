import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import ModelNotReadyError
from app.transcription.local import MODEL_CACHE, _model_is_downloaded, _repo_id, transcribe_local
from app.utils import ffmpeg_exe


@pytest.fixture(autouse=True)
def clear_model_cache():
    MODEL_CACHE.clear()
    yield
    MODEL_CACHE.clear()


# ------------------------------------------------------------------
# ffmpeg_exe()
# ------------------------------------------------------------------

def test_ffmpeg_exe_dev_mode():
    with patch.object(sys, "frozen", False, create=True):
        assert ffmpeg_exe() == "ffmpeg"


def test_ffmpeg_exe_frozen(tmp_path):
    fake_exe = str(tmp_path / "obsinote.exe")
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", fake_exe):
        result = ffmpeg_exe()
    assert result == os.path.join(str(tmp_path), "ffmpeg.exe")


# ------------------------------------------------------------------
# _model_is_downloaded()
# ------------------------------------------------------------------

def test_model_not_downloaded_missing_dir(tmp_path):
    assert _model_is_downloaded(str(tmp_path), "large-v3-turbo") is False


def test_model_not_downloaded_empty_cache_dir(tmp_path):
    # large-v3-turbo maps to mobiuslabsgmbh/faster-whisper-large-v3-turbo
    (tmp_path / "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo").mkdir()
    assert _model_is_downloaded(str(tmp_path), "large-v3-turbo") is False


def test_model_downloaded_non_empty_cache_dir(tmp_path):
    cache = tmp_path / "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo"
    cache.mkdir()
    (cache / "config.json").write_text("{}", encoding="utf-8")
    assert _model_is_downloaded(str(tmp_path), "large-v3-turbo") is True


def test_model_downloaded_checks_correct_model_name(tmp_path):
    # large-v3 is present but large-v3-turbo is not
    cache = tmp_path / "models--Systran--faster-whisper-large-v3"
    cache.mkdir()
    (cache / "config.json").write_text("{}", encoding="utf-8")
    assert _model_is_downloaded(str(tmp_path), "large-v3-turbo") is False
    assert _model_is_downloaded(str(tmp_path), "large-v3") is True


# ------------------------------------------------------------------
# _repo_id() — HuggingFace repo mapping
# ------------------------------------------------------------------

def test_repo_id_large_v3_turbo():
    assert _repo_id("large-v3-turbo") == "mobiuslabsgmbh/faster-whisper-large-v3-turbo"


def test_repo_id_large_v3():
    assert _repo_id("large-v3") == "Systran/faster-whisper-large-v3"


def test_repo_id_unknown_falls_back_to_systran():
    assert _repo_id("no-such-model") == "Systran/faster-whisper-no-such-model"


# ------------------------------------------------------------------
# transcribe_local() — error paths
# ------------------------------------------------------------------

def test_transcribe_local_missing_audio_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        transcribe_local("/nonexistent/audio.mp3", "cs", None, "")


def test_transcribe_local_model_not_ready_raises(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    model_dir = tmp_path / "models"
    model_dir.mkdir()

    with patch("app.transcription.local.cfg") as mock_cfg:
        mock_cfg.load.return_value = {
            "whisper_model": "large-v3-turbo",
            "whisper_model_dir": str(model_dir),
        }
        with pytest.raises(ModelNotReadyError):
            transcribe_local(str(audio), "cs", None, "")


# ------------------------------------------------------------------
# transcribe_local() — language mapping
# ------------------------------------------------------------------

def _make_mock_model(segments=None):
    mock_info = MagicMock()
    mock_info.duration = 2.0
    mock_info.language = "en"
    mock_info.language_probability = 0.99
    mock_model = MagicMock()
    mock_model.transcribe.return_value = (segments or [], mock_info)
    return mock_model


def test_transcribe_local_auto_passes_none_to_whisper(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    mock_model = _make_mock_model()

    with patch("app.transcription.local.cfg") as mock_cfg, \
         patch("app.transcription.local._load_model", return_value=mock_model):
        mock_cfg.load.return_value = {
            "whisper_model": "large-v3-turbo",
            "whisper_model_dir": "/models",
        }
        transcribe_local(str(audio), "auto", None, "glossary hint")

    _, kwargs = mock_model.transcribe.call_args
    assert kwargs["language"] is None


def test_transcribe_local_explicit_language_passed_through(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    mock_model = _make_mock_model()

    with patch("app.transcription.local.cfg") as mock_cfg, \
         patch("app.transcription.local._load_model", return_value=mock_model):
        mock_cfg.load.return_value = {
            "whisper_model": "large-v3-turbo",
            "whisper_model_dir": "/models",
        }
        transcribe_local(str(audio), "cs", None, "")

    _, kwargs = mock_model.transcribe.call_args
    assert kwargs["language"] == "cs"


def test_transcribe_local_glossary_used_as_initial_prompt(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    mock_model = _make_mock_model()

    with patch("app.transcription.local.cfg") as mock_cfg, \
         patch("app.transcription.local._load_model", return_value=mock_model):
        mock_cfg.load.return_value = {
            "whisper_model": "large-v3-turbo",
            "whisper_model_dir": "/models",
        }
        transcribe_local(str(audio), "cs", None, "Jira, PR, Confluence")

    _, kwargs = mock_model.transcribe.call_args
    assert kwargs["initial_prompt"] == "Jira, PR, Confluence"


# ------------------------------------------------------------------
# transcribe_local() — transcript assembly
# ------------------------------------------------------------------

def test_transcribe_local_joins_segments(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")

    seg1 = MagicMock(); seg1.text = "Hello "; seg1.end = 1.0
    seg2 = MagicMock(); seg2.text = " world"; seg2.end = 2.0
    mock_model = _make_mock_model(segments=[seg1, seg2])

    with patch("app.transcription.local.cfg") as mock_cfg, \
         patch("app.transcription.local._load_model", return_value=mock_model):
        mock_cfg.load.return_value = {
            "whisper_model": "large-v3-turbo",
            "whisper_model_dir": "/models",
        }
        result = transcribe_local(str(audio), "en", None, "")

    assert result == "Hello\nworld"


def test_transcribe_local_empty_segments_returns_empty_string(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")
    mock_model = _make_mock_model(segments=[])

    with patch("app.transcription.local.cfg") as mock_cfg, \
         patch("app.transcription.local._load_model", return_value=mock_model):
        mock_cfg.load.return_value = {
            "whisper_model": "large-v3-turbo",
            "whisper_model_dir": "/models",
        }
        result = transcribe_local(str(audio), "cs", None, "")

    assert result == ""


# ------------------------------------------------------------------
# transcribe() dispatcher
# ------------------------------------------------------------------

def test_dispatcher_unknown_provider_raises(tmp_path):
    from app.transcription import transcribe

    with patch("app.transcription.cfg") as mock_cfg, \
         patch("app.transcription.build_whisper_prompt", return_value=""):
        mock_cfg.load.return_value = {
            "transcription_provider": "deepgram",
            "language": "cs",
        }
        with pytest.raises(ValueError, match="Unknown transcription_provider"):
            transcribe("/some/audio.mp3")


def test_dispatcher_whisper_local_calls_transcribe_local(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")

    from app.transcription import transcribe

    with patch("app.transcription.cfg") as mock_cfg, \
         patch("app.transcription.build_whisper_prompt", return_value="hint"), \
         patch("app.transcription.local.transcribe_local", return_value="result") as mock_local:
        mock_cfg.load.return_value = {
            "transcription_provider": "whisper_local",
            "language": "en",
        }
        result = transcribe(str(audio), job_id="job-1")

    mock_local.assert_called_once_with(str(audio), "en", "job-1", "hint")
    assert result == "result"


def test_dispatcher_passes_language_from_config(tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"fake")

    from app.transcription import transcribe

    with patch("app.transcription.cfg") as mock_cfg, \
         patch("app.transcription.build_whisper_prompt", return_value=""), \
         patch("app.transcription.local.transcribe_local", return_value="") as mock_local:
        mock_cfg.load.return_value = {
            "transcription_provider": "whisper_local",
            "language": "de",
        }
        transcribe(str(audio))

    _, args, _ = mock_local.mock_calls[0]
    assert args[1] == "de"
