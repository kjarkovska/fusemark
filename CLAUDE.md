# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Project

**ObsiNote** — a local Windows 11 desktop app for recording meeting audio, transcribing it locally with faster-whisper, and generating structured Czech meeting notes into an Obsidian vault via Claude Haiku 3.5 API.

Audio never leaves the machine. Recording and processing are fully decoupled so back-to-back meetings work seamlessly.

## Current Status

**v0.9.1: Bug fixes — datepicker popup now dark (color-scheme: dark); uploaded notes now use selected meeting date in content (date_str threaded through generate_notes in all providers); audio import modal pre-fills today's date; Tests: 334 passed.**

- `app/recorder.py` — dual-stream capture (WASAPI loopback + mic) via `pyaudiowpatch`; ffmpeg mixes to mp3
- `app/config.py` — load/save `config.json`
- `app/queue.py` — SQLite job queue, full CRUD, state machine, startup recovery
- `app/worker.py` — fully wired: transcribe -> generate -> save note; re-fetches job after transcription (stale dict bug fix); accepts optional `config_loader` callable for testability
- `app/transcriber.py` — faster-whisper wrapper, Czech forced, glossary initial_prompt, progress reporting to SQLite
- `app/glossary.py` — load glossary.json, build Whisper prompt, add terms, open in VSCode
- `app/notemaker.py` — Claude Haiku 3.5: generates Czech notes, suggests glossary terms; API key via keyring
- `app/tray.py` — tray icon; icon bitmap only updated from main thread (Win32 safety); menu updates are thread-safe
- `app/server.py` — Flask routes; delegates recording lifecycle to `RecordingService`
- `app/recording_service.py` — recording start/stop, recorder state, tray notifications (extracted from server.py R1)
- `app/main.py` — entrypoint; worker + Flask on background threads, tray on main thread
- `templates/`, `static/` — dark UI with recorder, jobs panel, settings page
- `app/autostart.py` — Windows registry auto-start (HKCU, no admin needed); toggle in Settings
- Run with `python -m app.main`; exit via tray right-click → Quit (Ctrl+C blocked by pystray)
- Claude sometimes wraps JSON in markdown fences — stripped in `suggest_glossary_terms`
- Run all modules with `python -m app.X` (not `python app/X.py`) — avoids import errors
- Reading transcript files: use `errors='replace'` — terminal redirects write CP1250, not UTF-8
- Currently using `small` Whisper model — sufficient in initial test; upgrade to large-v3 if quality is lacking
- BT note: Windows switches JBL to HSP/HFP when mic opens. Windows OS limitation — unavoidable. Acceptable for transcription quality.
- P5.5: `app/i18n.py` — `TRANSLATIONS` dict ("en"/"cs") + `get_strings(lang)`; all templates receive `t=get_strings(...)` from server; `window.STRINGS` injected before app.js; Settings page has "Interface language" selector; saving settings triggers full page reload so language takes effect immediately; Tests: 225 passed.
- P6: 5-step first-run wizard (`templates/wizard.html`); gated on `setup_complete: false` in config; `GET /` redirects to `/wizard` when false; 7 wizard routes in server.py; `test_connection(key)` added to all 3 LLM providers; pywebview FOLDER_DIALOG for vault path; dev fallback returns `{dev_mode: true}`; Settings → Re-run Setup Wizard resets flag; all wizard strings bilingual (en+cs); Tests: 239 passed.
- P7: Settings UI extended — Whisper model `<select>` replaced with visual table (per-row download badge + progress bar); API key rows show only the active provider (JS toggle); "Test" button tests entered key or stored keyring key (`/api/test-llm-stored`); Recording housekeeping section (size, auto-delete toggle, max-GB, delete-processed button); Update section (version display, check-updates toggle, "Check now" → GitHub releases API); `app/version.py` created; 4 new server routes (`/recordings/size`, `/recordings/cleanup`, `/api/test-llm-stored`, `/update-check`); ~25 new i18n strings (en+cs); Tests: 247 passed.
- P8: `keep_audio` migration added to `queue.py` init_db() · `worker.py` auto-deletes recording after "done" via `_maybe_delete_recording()` (respects `keep_audio` flag) and enforces GB size cap via `_enforce_size_limit()` · `server.py` `cleanup_recordings()` utility replaces old route body — respects `keep_audio`, handles done+error+orphans · jobs panel footer shows "Total size: X MB/GB"; Tests: 261 passed.
- Refactor R1: `app/recording_service.py` created — recording lifecycle extracted from `server.py` module globals · `app/transcription/__init__.py` exports `TranscribeCallable`, `app/llm/__init__.py` exports `GenerateNotesCallable` + `SuggestTermsCallable` type aliases · `Worker.__init__` accepts `config_loader` param; `docs/ARCHITECTURE.md` updated with as-built diagram + hexagonal review; Tests: 299 passed.
- P9: `app/updater.py` created — `check_for_update()` (24h throttle, respects `check_updates` flag, silent on network errors, caches result to config as `latest_known_version`/`latest_known_url`) + `get_cached_status()` · `GET /update-status` route reads cache without network call · `POST /open-url` opens URLs in system browser (https:// validated) · startup daemon thread in `main.py` calls `check_for_update()` after Flask starts · green update banner added to `index.html` (hidden by default, JS polls `/update-status` on load, Dismiss hides for session) · 2 new i18n strings (en+cs); Tests: 312 passed.

Update this section at the end of every session.

## Documentation

All project documentation lives in the [`docs/`](docs/) folder:

- [`docs/BRIEF.md`](docs/BRIEF.md) — Product brief: goals, architecture, user flow, UI design, data model, cost estimate, and out-of-scope items.
- [`docs/PLAN.md`](docs/PLAN.md) — Implementation plan: phased build order (Phase 1–6), project file structure, per-phase tasks and test commands, and recommendations for working with Claude Code.

**Always read both docs files at the start of a session before making any changes.**

## How to Work on This Project

The plan is phase-based. Start each session by stating which phase you are on:

> "Read docs/BRIEF.md and docs/PLAN.md. We are working on Phase X — [phase goal]."

Work phase by phase. Each phase must reach a testable state before moving to the next. **Phase 1 (audio capture) is the highest risk** — test on real hardware before continuing.

After each phase:
```bash
git add .
git commit -m "Phase X - [description] complete"
```

## Tech Stack

| Layer | Technology |
|---|---|
| Audio capture | Python + `sounddevice` (WASAPI loopback + mic, separate streams) |
| Transcription | `faster-whisper large-v3` (local, CPU) |
| Note generation | Claude Haiku 3.5 API (`anthropic`) |
| UI | Flask + HTML (local web app) |
| System tray | `pystray` |
| Job queue | SQLite (`sqlite3`) |
| API key storage | Windows Credential Manager (`keyring`) |
| Glossary | `glossary.json` |
| Output | Markdown → Obsidian vault |

## Key Constraints

- **Windows 11 only** — WASAPI loopback is Windows-specific; do not suggest cross-platform alternatives
- **Python 3.11+** — fall back to a venv with 3.11 or 3.12 if faster-whisper has issues with 3.13
- **ffmpeg must be in PATH** — required for pydub audio processing
- **API key in Windows Credential Manager only** — never store in `.env`, `config.json`, or any file
- **Paths are Windows paths** — always use `os.path.join()`, never hardcode forward slashes

## Do Not

- Refactor or modify code from completed phases unless explicitly asked
- Switch libraries that are already decided in the tech stack
- Create files outside the project structure defined in `docs/PLAN.md`
- Suggest Linux/macOS-specific solutions
- Move on to the next phase before the current one has a passing CLI test