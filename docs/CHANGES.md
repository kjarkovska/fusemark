# Granola-CZ — Planned Changes

A running list of requested changes. Each section tracks what needs to be done, which files are affected, and any known constraints. This doc will grow as new requests are added; once finalized it becomes the implementation plan.

---

## 1. Standalone Window via PyWebView

**Goal:** Replace browser-based UI with a native standalone window (no address bar, no tabs, no browser chrome).

**Approach:** Use `pywebview` which wraps Microsoft Edge WebView2 — pre-installed on Windows 11. Flask stays unchanged; pywebview renders the existing HTML/CSS/JS.

### Key conflict to resolve
`pystray` currently runs on the **main thread** (Win32 requirement).
`pywebview` (`webview.start()`) also requires the **main thread**.
→ Solution: call `pystray`'s `icon.run_detached()` to move it to a background thread, freeing the main thread for pywebview.

### Changes required

| File | Change |
|---|---|
| `requirements.txt` | Add `pywebview` |
| `app/main.py` | Switch pystray to `run_detached()`; launch pywebview on main thread instead of opening browser |
| `app/tray.py` | Replace `webbrowser.open()` in the "Open" menu item with a call to show/focus the pywebview window |
| `app/server.py` | Remove `webbrowser.open()` startup call |

### Implementation notes
- `webview.create_window(title, url, width, height)` → create before `webview.start()`
- Window title: `"Granola-CZ"`; reasonable default size e.g. 900×700
- The pywebview window reference should be accessible from tray callbacks so "Open" can call `window.show()` or `window.minimize()` toggle
- When the pywebview window is closed by the user, trigger a clean shutdown (stop worker + tray) — wire via `webview.start(on_top=False)` and the window's `closed` event or post-`webview.start()` cleanup
- Keep DevTools disabled in production (default); can be enabled via `webview.start(debug=True)` for development

### Open questions
- Should closing the window quit the app entirely, or minimize it to tray?

---

<!-- Add further change requests below this line -->
