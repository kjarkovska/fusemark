"""
tray.py — System tray icon for Granola-CZ

States:
  idle      — grey icon, menu shows Start Recording
  recording — red icon, menu shows Stop Recording

Icon bitmap is set only from tray menu callbacks (main thread).
When recording is toggled from the web UI (Flask thread), only the menu
is updated — bitmap changes are skipped to avoid Win32 thread-safety issues.

The tray runs on the main thread (pystray requirement on Windows).
Flask and the worker run on background threads.
"""

from PIL import Image, ImageDraw
import pystray


def _make_icon(color):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=color)
    return img


ICON_IDLE = _make_icon((100, 100, 100, 255))
ICON_RECORDING = _make_icon((220, 40, 40, 255))


class TrayIcon:
    def __init__(self, on_start, on_stop, on_open, on_quit):
        self._on_start = on_start
        self._on_stop = on_stop
        self._on_open = on_open
        self._on_quit = on_quit
        self._recording = False
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
        icon.icon = ICON_RECORDING
        icon.menu = self._menu()

    def _stop(self, icon, item):
        self._on_stop()
        self._recording = False
        icon.icon = ICON_IDLE
        icon.menu = self._menu()

    def _open(self, icon, item):
        self._on_open()

    def _quit(self, icon, item):
        self.stop()
        self._on_quit()

    # ------------------------------------------------------------------
    # Called from Flask thread — only update menu, never the icon bitmap
    # ------------------------------------------------------------------

    def set_recording(self, recording):
        self._recording = recording
        if self._icon:
            self._icon.menu = self._menu()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def run(self):
        """Start the tray icon. Blocks until quit (must run on main thread)."""
        self._icon = pystray.Icon(
            "granola-cz",
            ICON_IDLE,
            "Granola-CZ",
            menu=self._menu(),
        )
        self._icon.run()

    def stop(self):
        if self._icon:
            self._icon.stop()
