"""
main.py — Entrypoint for ObsiNote

Starts three components:
  1. Worker thread  — background job processor
  2. Flask thread   — web UI server on localhost:5000
  3. Tray icon      — runs on main thread (pystray requirement on Windows)

Usage:
  python -m app.main
"""

import threading

from app import queue as q
from app.worker import Worker
from app.tray import TrayIcon
from app import server


def main():
    q.init_db()
    q.recover_interrupted_jobs()

    # Start background worker
    worker = Worker()
    worker.start()

    # Wire tray callbacks to server recording controls
    tray = TrayIcon(
        on_start=lambda: server.start_recording(),
        on_stop=lambda: server.stop_recording(),
        on_open=lambda: server.open_browser(),
        on_quit=lambda: (worker.stop(), tray.stop()),
    )
    server.set_tray(tray)
    worker.on_transcribing = tray.set_transcribing

    # Start Flask in a background thread
    flask_thread = threading.Thread(
        target=server.run,
        kwargs={"port": 5000, "open_on_start": True},
        daemon=True,
    )
    flask_thread.start()

    # Tray blocks the main thread until Quit
    tray.run()


if __name__ == "__main__":
    main()
