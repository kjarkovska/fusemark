import os
import sys


def ffmpeg_exe() -> str:
    """Return the correct ffmpeg executable path for the current runtime."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe")
    return "ffmpeg"
