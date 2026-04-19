"""
main.py — Entrypoint for ObsiNote

Starts four components:
  1. Worker thread  — background job processor
  2. Flask thread   — web UI server on localhost:5000
  3. Tray icon      — background thread (pystray run_detached)
  4. pywebview      — native window on the main thread (Win32 requirement)

Closing the window hides it to tray. Only tray → Quit exits the app.

Window icons (Win32 WM_SETICON allows independent small/big icons):
  ICON_SMALL (title bar) — white always
  ICON_BIG   (taskbar)   — reflects status: grey/red/blue; white on failure

Usage:
  python -m app.main
"""

import ctypes
import logging
import os
import time
import threading
from logging.handlers import RotatingFileHandler

import webview
from PIL import Image

from app import queue as q
from app.worker import Worker
from app.tray import TrayIcon
from app import server

_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_ASSETS = os.path.join(_PROJECT_ROOT, "assets")

# Cached window handle — set once the pywebview window finishes loading
_hwnd = None


# ------------------------------------------------------------------
# Logging setup
# ------------------------------------------------------------------

def _setup_logging():
    from app import config as cfg
    config = cfg.load()
    level_name = config.get("log_level", "DEBUG").upper()
    file_level = getattr(logging, level_name, logging.DEBUG)

    logs_dir = os.path.join(_PROJECT_ROOT, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "obsinote.log")

    fmt = logging.Formatter("%(asctime)s [%(levelname)-8s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(fmt)

    root = logging.getLogger()
    root.setLevel(file_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Suppress Werkzeug per-request log spam on console
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


# ------------------------------------------------------------------
# Icon helpers
# ------------------------------------------------------------------

def _build_icons():
    """
    Generate per-state ICO files from assets/icon.png if missing.
    Returns a dict: status -> ico_path
    """
    png = os.path.join(_ASSETS, "icon.png")
    base = Image.open(png).convert("RGBA")
    _, _, _, alpha = base.split()
    sizes = [(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)]

    states = {
        "white":        (255, 255, 255, 255),
        "idle":         (120, 120, 120, 255),
        "recording":    (210,  40,  40, 255),
        "transcribing": ( 40, 120, 210, 255),
    }
    icons = {}
    for name, color in states.items():
        ico_path = os.path.join(_ASSETS, f"icon_{name}.ico")
        if not os.path.exists(ico_path):
            tinted = Image.new("RGBA", base.size, color)
            tinted.putalpha(alpha)
            tinted.save(ico_path, format="ICO", sizes=sizes)
        icons[name] = ico_path
    return icons


def _win32_set_icons(small_path=None, big_path=None):
    """Set title-bar (small) and/or taskbar (big) icon via Win32 SendMessage."""
    if not _hwnd:
        return

    # Must set restype to c_void_p — default c_int truncates 64-bit handles
    user32 = ctypes.windll.user32
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.FindWindowW.restype = ctypes.c_void_p
    user32.SendMessageW.restype = ctypes.c_long

    LR_LOADFROMFILE = 0x0010
    IMAGE_ICON = 1
    WM_SETICON = 0x0080
    ICON_SMALL, ICON_BIG = 0, 1

    if small_path:
        h = user32.LoadImageW(None, small_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if h:
            user32.SendMessageW(_hwnd, WM_SETICON, ICON_SMALL, h)
    if big_path:
        h = user32.LoadImageW(None, big_path, IMAGE_ICON, 48, 48, LR_LOADFROMFILE)
        if h:
            user32.SendMessageW(_hwnd, WM_SETICON, ICON_BIG, h)


def main():
    # Single-instance guard — create a named mutex; exit if another instance owns it
    _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\ObsiNote")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        import sys
        sys.exit(0)

    _setup_logging()

    # Give ObsiNote a unique Windows identity — prevents grouping under python.exe
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ObsiNote.App")

    icons = _build_icons()

    q.init_db()
    q.recover_interrupted_jobs()

    from app import glossary
    glossary.migrate_if_needed()

    # Start background worker
    worker = Worker()
    worker.start()

    # Create pywebview window before webview.start()
    window = webview.create_window(
        "ObsiNote",
        "http://127.0.0.1:5000",
        width=960,
        height=720,
        min_size=(600, 500),
    )

    def _on_loaded():
        """Cache HWND and apply initial icons once the window is ready."""
        global _hwnd
        # Use pywebview's native handle; fall back to FindWindowW
        try:
            _hwnd = window.native_handle
        except AttributeError:
            _hwnd = None
        if not _hwnd:
            ctypes.windll.user32.FindWindowW.restype = ctypes.c_void_p
            _hwnd = ctypes.windll.user32.FindWindowW(None, "ObsiNote")
        _win32_set_icons(small_path=icons["white"], big_path=icons["idle"])

    def _on_closing():
        """Hide window instead of closing it. Only Quit destroys it."""
        window.hide()
        return False

    window.events.loaded += _on_loaded
    window.events.closing += _on_closing

    # Status callbacks — update tray icon and taskbar icon together
    def _on_transcribing(active):
        tray.set_transcribing(active)
        _win32_set_icons(big_path=icons["transcribing"] if active else icons["idle"])

    def _on_start():
        server.start_recording()
        _win32_set_icons(big_path=icons["recording"])

    def _on_stop():
        server.stop_recording()
        _win32_set_icons(big_path=icons["idle"])

    def _quit():
        worker.stop()
        tray.stop()
        window.destroy()

    tray = TrayIcon(
        on_start=_on_start,
        on_stop=_on_stop,
        on_open=lambda: window.show(),
        on_quit=_quit,
    )
    server.set_tray(tray)
    worker.on_transcribing = _on_transcribing
    worker.on_tooltip = tray.set_tooltip

    # Start Flask in a background thread
    flask_thread = threading.Thread(
        target=server.run,
        kwargs={"port": 5000},
        daemon=True,
    )
    flask_thread.start()

    # Start tray in background thread — frees main thread for pywebview
    tray.run_detached()

    # Wait for Flask to be ready before pywebview loads the URL
    time.sleep(0.8)

    # pywebview blocks the main thread until all windows are destroyed
    webview.start(icon=icons["white"])


if __name__ == "__main__":
    main()
