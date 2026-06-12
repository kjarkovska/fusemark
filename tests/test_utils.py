import sys
from unittest.mock import patch

import app.utils as utils


def test_ffmpeg_exe_returns_bare_string_in_dev():
    assert utils.ffmpeg_exe() == "ffmpeg"


def test_ffmpeg_exe_returns_bundled_path_when_frozen(tmp_path):
    fake_exe = str(tmp_path / "FuseMark.exe")
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", fake_exe):
        result = utils.ffmpeg_exe()
    assert result == str(tmp_path / "ffmpeg.exe")


def test_ffmpeg_available_true_when_on_path():
    with patch.object(utils.shutil, "which", return_value=r"C:\ffmpeg\ffmpeg.exe"):
        assert utils.ffmpeg_available() is True


def test_ffmpeg_available_false_when_not_on_path():
    with patch.object(utils.shutil, "which", return_value=None):
        assert utils.ffmpeg_available() is False


def test_ffmpeg_available_checks_file_next_to_exe_when_frozen(tmp_path):
    fake_exe = str(tmp_path / "FuseMark.exe")
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", fake_exe):
        assert utils.ffmpeg_available() is False
        (tmp_path / "ffmpeg.exe").write_bytes(b"")
        assert utils.ffmpeg_available() is True
