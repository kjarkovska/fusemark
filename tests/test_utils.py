import sys
from unittest.mock import patch

import app.utils as utils


def test_ffmpeg_exe_returns_bare_string_in_dev():
    assert utils.ffmpeg_exe() == "ffmpeg"


def test_ffmpeg_exe_returns_bundled_path_when_frozen(tmp_path):
    fake_exe = str(tmp_path / "ObsiNote.exe")
    with patch.object(sys, "frozen", True, create=True), \
         patch.object(sys, "executable", fake_exe):
        result = utils.ffmpeg_exe()
    assert result == str(tmp_path / "ffmpeg.exe")
