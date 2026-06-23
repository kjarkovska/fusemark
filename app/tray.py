"""
tray.py — System tray icon for FuseMark

States:
  idle          — grey icon, menu shows Start Recording
  recording     — red icon, menu shows Stop Recording
  transcribing  — blue icon (set from worker thread via set_transcribing())

Icon bitmap is set only from tray menu callbacks (main thread) for recording
state, because pystray's Win32 bitmap update must come from the message-pump
thread.  The transcribing state uses the same safety: set_transcribing() only
updates the menu; the bitmap is updated lazily when a menu action fires.

The tray runs on the main thread (pystray requirement on Windows).
Flask and the worker run on background threads.
"""

import os
import sys

from PIL import Image
import pystray


def _tint(path, color):
    """Return a copy of the PNG at `path` with all pixels replaced by `color`."""
    img = Image.open(path).convert("RGBA")
    _, _, _, a = img.split()
    colored = Image.new("RGBA", img.size, color)
    colored.putalpha(a)
    return colored


_BASE = sys._MEIPASS if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(__file__))
_ICON_PATH = os.path.join(_BASE, "assets", "icon.png")
ICON_IDLE          = _tint(_ICON_PATH, (120, 120, 120, 255))
ICON_RECORDING     = _tint(_ICON_PATH, (210,  40,  40, 255))
ICON_TRANSCRIBING  = _tint(_ICON_PATH, ( 40, 120, 210, 255))

_ICON_MAP = {"idle": ICON_IDLE, "recording": ICON_RECORDING, "transcribing": ICON_TRANSCRIBING}


def icon_for_state(recording: bool, transcribing: bool) -> str:
    """Return the icon state key given recording/transcribing flags.
    Recording takes precedence over transcribing."""
    if recording:
        return "recording"
    if transcribing:
        return "transcribing"
    return "idle"


class TrayIcon:
    def __init__(self, on_start, on_stop, on_open, on_quit):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_open = on_open
        self._on_quit = on_quit
        self._recording = False
        self._transcribing = False
        self._icon = None

    def _menu(self):
        if self._recording:
            return pystray.Menu(
                pystray.MenuItem("Stop Recording", self._stop),
                pystray.MenuItem("Open", self._open),
                pystray.MenuItem("Quit", self._quit),
            )
        return pystray.Menu(
            pystray.MenuItem("Start Recording", self._start),
            pystray.MenuItem("Open", self._open),
            pystray.MenuItem("Quit", self._quit),
        )

    # ------------------------------------------------------------------
    # Tray menu callbacks — run on the main thread, safe to update icon
    # ------------------------------------------------------------------

    def _start(self, icon, item):
        self._on_start()
        self._recording = True
        self._transcribing = False
        icon.icon = ICON_RECORDING
        icon.menu = self._menu()

    def _stop(self, icon, item):
        self._on_stop()
        self._recording = False
        self._transcribing = False
        icon.icon = ICON_IDLE
        icon.menu = self._menu()

    def _open(self, icon, item):
        self._on_open()

    def _quit(self, icon, item):
        self.stop()
        self._on_quit()

    # ------------------------------------------------------------------
    # Called from background threads — safe: pystray uses PostMessage for
    # icon updates on Windows, which is thread-safe (async message queue).
    # ------------------------------------------------------------------

    def set_recording(self, recording):
        self._recording = recording
        if self._icon:
            self._icon.icon = _ICON_MAP[icon_for_state(self._recording, self._transcribing)]
            self._icon.menu = self._menu()

    def set_transcribing(self, transcribing):
        self._transcribing = transcribing
        if self._icon:
            self._icon.icon = _ICON_MAP[icon_for_state(self._recording, self._transcribing)]
            self._icon.menu = self._menu()

    def set_tooltip(self, text):
        if self._icon:
            self._icon.title = text[:127]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run_detached(self):
        """Start the tray icon in a background thread (non-blocking)."""
        self._icon = pystray.Icon(
            "fusemark",
            ICON_IDLE,
            "FuseMark",
            menu=self._menu(),
        )
        self._icon.run_detached()

    def stop(self):
        if self._icon:
            self._icon.stop()
