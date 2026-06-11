import os
import shutil
import sys


def ffmpeg_exe() -> str:
    """Return the correct ffmpeg executable path for the current runtime."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe")
    return "ffmpeg"


def ffmpeg_available() -> bool:
    """Return True if the ffmpeg binary can be located for the current runtime.

    Used for a clear startup warning — without ffmpeg, recording and audio
    import fail deep inside a subprocess with a confusing error.
    """
    exe = ffmpeg_exe()
    if os.path.isabs(exe):  # packaged build: ffmpeg.exe next to the executable
        return os.path.isfile(exe)
    return shutil.which(exe) is not None  # dev: resolve via PATH
