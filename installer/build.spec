# -*- mode: python ; coding: utf-8 -*-
"""
build.spec — PyInstaller spec for ObsiNote (Phase P11 packaging).

Build:
    pip install pyinstaller
    pyinstaller installer/build.spec

Output:
    dist/ObsiNote/ObsiNote.exe   (onedir — Inno Setup wraps this directory)

Notes:
  - onedir (not onefile): avoids slow self-extraction on every launch.
  - PortAudio (pyaudiowpatch) and ctranslate2 (faster-whisper backend) ship DLLs
    that PyInstaller does NOT auto-detect — they are collected explicitly below.
    Missing them means the app launches but recording / transcription silently fail.
  - The Whisper model is downloaded at runtime to whisper_model_dir; it is never bundled.
  - ffmpeg.exe / ffprobe.exe are NOT bundled here — Inno Setup installs them next to
    ObsiNote.exe (ffmpeg_exe() in app/utils.py finds them via sys.frozen).
"""

import os
import sys

from PIL import Image
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
ASSETS = os.path.join(PROJECT_ROOT, "assets")
sys.path.insert(0, PROJECT_ROOT)

# --- Icons -----------------------------------------------------------------
# The app's per-state tray/window ICOs are normally generated at runtime, but an
# installed build under Program Files is read-only. Pre-generate them here and
# bundle them so the runtime guard (`if not os.path.exists`) skips writing.
from app.main import _build_icons  # noqa: E402

_build_icons()
_app_ico = os.path.join(ASSETS, "icon.ico")
if not os.path.exists(_app_ico):
    Image.open(os.path.join(ASSETS, "icon.png")).convert("RGBA").save(
        _app_ico, format="ICO", sizes=[(256, 256), (48, 48), (32, 32), (16, 16)]
    )

# --- Binaries & data -------------------------------------------------------
binaries = (
    collect_dynamic_libs("pyaudiowpatch")   # PortAudio DLLs
    + collect_dynamic_libs("ctranslate2")   # faster-whisper backend DLLs
)

datas = (
    [
        (os.path.join(PROJECT_ROOT, "templates"), "templates"),
        (os.path.join(PROJECT_ROOT, "static"), "static"),
        (ASSETS, "assets"),
    ]
    + collect_data_files("faster_whisper")
    + collect_data_files("ctranslate2")
    + collect_data_files("webview")
)

hiddenimports = [
    "pyaudiowpatch",
    "faster_whisper",
    "ctranslate2",
    "webview",
    "anthropic",
    "openai",
    "mistralai",
    "keyring",
    "keyring.backends.Windows",   # Windows Credential Manager backend
]

# --- Build graph -----------------------------------------------------------
a = Analysis(
    [os.path.join(PROJECT_ROOT, "app", "main.py")],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ObsiNote",
    debug=False,
    strip=False,
    upx=False,            # UPX can corrupt native DLLs — leave off
    console=False,        # no terminal window
    icon=_app_ico,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="ObsiNote",
)
