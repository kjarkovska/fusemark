# Granola-CZ — Project Knowledge

> Comprehensive reference for use as Claude project knowledge. Reflects state as of Phase 6 (complete), with planned changes noted.

---

## What It Is

A local Windows 11 desktop app for recording meeting audio, transcribing it locally, and generating structured Czech meeting notes into an Obsidian vault. Inspired by Granola.ai but privacy-first: audio never leaves the machine; only the text transcript is sent to the Claude API.

**Target user:** Single user, ASUS ExpertBook laptop, Windows 11 Pro, ~8–12 hours of meetings/week (Teams, Zoom, browser-based calls), frequent Bluetooth headset use, frequent back-to-back meetings.

**Cost:** ~$0.67/month (Claude Haiku 3.5 API only; transcription is free/local).

---

## Architecture Overview

```
Audio capture (WASAPI loopback + mic — two separate streams)
        ↓
  .mp3 file (stored locally in app/recordings/)
        ↓
  Job Queue (SQLite — persistent, survives restarts)
        ↓
  faster-whisper (local, CPU, background worker thread)
        ↓
  Transcript + Scratch notes + Context + Glossary
        ↓
  Claude Haiku 3.5 API
        ↓
  .md file → Obsidian vault
        ↓
  New term suggestions → glossary.json (user approves in UI)
```

**Process model:**
- Main thread: pystray tray icon (Win32 requirement)
- Background thread 1: Flask web server (port 5000, localhost only)
- Background thread 2: worker (transcribe → generate → save, serial queue)
- UI: browser opens at `http://127.0.0.1:5000` on startup

---

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Audio capture | `pyaudiowpatch` | WASAPI loopback on Windows; two separate streams mixed by ffmpeg |
| Transcription | `faster-whisper` | Local, CPU, Czech forced, glossary hotwords via initial_prompt |
| Note generation | `anthropic` (Claude Haiku 3.5) | Czech output always; API key via keyring |
| UI | Flask + vanilla HTML/CSS/JS | Dark VSCode-like theme; two pages (index + settings) |
| System tray | `pystray` + `Pillow` | Must run on main thread; icon is grey (idle) or red (recording) |
| Job queue | `sqlite3` (stdlib) | Persistent; worker auto-recovers interrupted jobs on startup |
| API key storage | `keyring` | Windows Credential Manager; never stored in files |
| Glossary | `glossary.json` | JSON file in project root; editable in VSCode |
| Audio mixing | `ffmpeg` (system dep, must be in PATH) | Mixes loopback + mic to .mp3 |
| Output | Markdown → Obsidian vault | Path configurable in settings |
| Auto-start | Windows registry HKCU | No admin needed; toggle in settings |

---

## Project File Structure

```
granola-cz/
├── CLAUDE.md                # Claude Code instructions
├── requirements.txt         # Python dependencies
├── glossary.json            # Term glossary (editable in VSCode)
├── config.json              # Vault path, audio devices, model size (auto-created)
├── jobs.db                  # SQLite job queue (auto-created)
├── app/
│   ├── main.py              # Entrypoint — launches worker + Flask + tray
│   ├── tray.py              # pystray icon and menu (main thread)
│   ├── server.py            # Flask routes (background thread)
│   ├── recorder.py          # Audio capture (WASAPI loopback + mic)
│   ├── worker.py            # Background job processor
│   ├── transcriber.py       # faster-whisper wrapper; progress → SQLite
│   ├── notemaker.py         # Claude Haiku 3.5; generates notes + glossary suggestions
│   ├── queue.py             # SQLite job queue CRUD + state machine
│   ├── config.py            # Load/save config.json
│   ├── autostart.py         # Windows registry auto-start toggle
│   └── glossary.py          # Load glossary, build Whisper prompt, add terms
├── templates/
│   ├── index.html           # Main recording interface
│   └── settings.html        # Settings screen
├── static/
│   ├── style.css            # Dark theme (#1e1e1e background)
│   └── app.js               # Frontend logic (polling, recording toggle)
├── docs/
│   ├── BRIEF.md             # Product brief
│   ├── PLAN.md              # Phased implementation plan
│   ├── CHANGES.md           # Planned future changes (running list)
│   └── PROJECT_KNOWLEDGE.md # This file
└── app/recordings/          # .mp3 files (auto-created)
```

---

## Module Responsibilities

### `app/main.py`
Entry point. Initializes DB, recovers interrupted jobs, starts worker thread, starts Flask thread, then runs pystray on the main thread (blocking). Flask opens the browser on startup (0.8s delay). Exit is via tray right-click → Quit (Ctrl+C is blocked by pystray).

### `app/server.py`
Flask app on `127.0.0.1:5000`. Global `_recorder` object protected by `_recorder_lock`. Routes:
- `GET /` — main UI
- `GET /settings` — settings page
- `POST /start` — start recording (params: `label`, `folder`)
- `POST /stop` — stop recording (param: `scratch_notes`)
- `GET /jobs` — all jobs as JSON
- `POST /jobs/<id>/context` — update job extra_context
- `POST /jobs/<id>/audio` — keep/delete audio decision
- `GET /status` — current recording state (`{recording: bool, job_id}`)
- `POST /settings/save` — save vault_path, whisper_model, audio devices
- `GET|POST /autostart` — query/toggle Windows auto-start
- `POST /open-glossary` — open glossary.json in VSCode
- `POST /api-key` — store API key in Windows Credential Manager

### `app/recorder.py`
Dual-stream capture using `pyaudiowpatch`. Records WASAPI loopback (system audio) and microphone as separate streams simultaneously. ffmpeg mixes them into a single .mp3. Audio files stored as `app/recordings/<job_id>.mp3`.

### `app/worker.py`
Serial background processor. Picks the oldest `queued` job, runs transcribe → generate → save. Re-fetches the job from SQLite after transcription (avoids stale dict bug). Loops continuously; sleeps briefly when queue is empty.

### `app/transcriber.py`
Wraps `faster-whisper`. Czech language forced. Glossary terms passed as `initial_prompt` for hotword boosting. Reports progress back to SQLite `extra_context` field so the UI can show a progress bar.

### `app/notemaker.py`
Calls Claude Haiku 3.5 API. Generates structured Czech meeting notes. Also suggests up to 5 new glossary terms (unconventional terms not in standard Czech/English dictionaries). Claude sometimes wraps JSON in markdown fences — stripped before parsing in `suggest_glossary_terms`.

### `app/queue.py`
SQLite CRUD for the jobs table. State machine: `recording → queued → transcribing → generating → done / error`. On startup, `recover_interrupted_jobs()` resets any `transcribing`/`generating` jobs back to `queued`.

### `app/tray.py`
pystray icon. Must run on the main thread (Win32 safety). Icon bitmap updated only from main thread. `set_recording()` method is called from Flask thread but only updates the menu (not the bitmap) to avoid Win32 threading issues. Menu: Start/Stop Recording, Open (launches browser), Quit.

### `app/config.py`
Load/save `config.json`. Stores: `vault_path`, `whisper_model`, output audio device, input audio device.

### `app/glossary.py`
Loads `glossary.json`. Builds Whisper `initial_prompt` from canonical terms + aliases. Provides `add_terms()` for appending new glossary entries. `open_in_vscode()` opens the file in VSCode.

### `app/autostart.py`
Reads/writes Windows registry key `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` to launch the app on login. No admin rights required.

---

## Job Queue Data Model

```sql
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  created_at TEXT,
  label TEXT,
  folder TEXT,
  recording_path TEXT,      -- temp path during recording
  audio_path TEXT,          -- final .mp3 path
  scratch_notes TEXT,
  extra_context TEXT,       -- user-added context; also used for progress %
  status TEXT,              -- recording/queued/transcribing/generating/done/error
  transcript TEXT,
  output_note_path TEXT,
  keep_audio INTEGER,       -- NULL=undecided, 1=keep, 0=delete
  error_message TEXT,
  updated_at TEXT
);
```

---

## Obsidian Output Structure

**Vault folder structure (example):**
```
Vault/
└── Meetings/
    ├── Projects/ProjectX/2026-03-10 Kickoff.md
    ├── 1on1/2026-03-12 Petr.md
    └── Other/2026-03-14 Standup.md
```

**Note template (generated by Claude):**
```markdown
---
date: 2026-03-10
type: meeting
tags: [meeting]
---

# 2026-03-10 Meeting Title

## Participants
## Context
## Summary
## Decisions
## Action Items
- [ ] Task — responsible person
## Notes

---
<details><summary>Transcript</summary>
[full transcript]
</details>
```

---

## Glossary File Format

`glossary.json` in project root:
```json
{
  "terms": [
    {
      "canonical": "Jira",
      "aliases": ["Yira", "Džira", "jira"],
      "context": "project management tool",
      "type": "product"
    }
  ]
}
```
- Canonical term + aliases → fed to Whisper as hotwords
- Full structured glossary → fed to Claude system prompt
- New terms suggested by Claude after each meeting; user approves in UI

---

## UI

**Two-page web app (Flask templates, dark VSCode-like theme):**

**index.html — Recorder + Jobs:**
- Header: "Granola-CZ" + link to Settings
- Recorder section: meeting label input, folder dropdown (from vault/Meetings/), timer, Start/Stop button (green/red), scratch notes textarea
- Jobs panel: auto-refreshes every 3s; shows status badge, progress bar, context input, audio decision buttons, note path link

**settings.html:**
- Vault path, Whisper model size, output device, input device
- API key (password field → Windows Credential Manager)
- Autostart toggle (Windows registry)
- Open Glossary in VSCode button

**Status badge labels (Czech):** Nahrávám / Ve frontě / Přepisuji / Generuji / Hotovo / Chyba

---

## Key Constraints

- **Windows 11 only** — WASAPI loopback is Windows-specific
- **Python 3.11+** — faster-whisper may have issues with 3.13; use venv with 3.11/3.12 if needed
- **ffmpeg must be in PATH** — required for audio mixing
- **API key in Windows Credential Manager only** — never in `.env`, `config.json`, or any file
- **Paths always via `os.path.join()`** — never hardcode forward slashes
- **Run as module** — `python -m app.main` (not `python app/main.py`) to avoid import errors
- **Read transcripts with `errors='replace'`** — terminal redirects write CP1250, not UTF-8
- **pystray on main thread** — Win32 requirement; icon bitmap only updated from main thread

---

## Known Quirks & Decisions

- **Bluetooth headset:** Windows switches JBL to HSP/HFP when mic opens — this is a Windows OS limitation. Two-stream capture avoids A2DP degradation but can't fully prevent the profile switch. Acceptable quality for transcription.
- **Claude JSON fences:** Claude sometimes wraps JSON in markdown code fences. `suggest_glossary_terms` strips these before `json.loads()`.
- **Whisper model:** Currently `small` — sufficient in initial testing. Upgrade to `large-v3` if quality is lacking (higher CPU/RAM usage, slower).
- **Stale dict bug:** Worker re-fetches job from SQLite after transcription rather than passing the job dict — the dict was stale after the transcriber updated the DB directly.
- **Tray thread safety:** `set_recording()` is called from Flask thread but only updates the pystray menu, never the icon bitmap. Bitmap updates happen only in menu callbacks (main thread).

---

## Planned Changes (as of 2026-04-10)

See `docs/CHANGES.md` for full details.

### 1. Standalone Window via PyWebView
Replace browser-based UI with a native standalone window using `pywebview` (wraps Edge WebView2, pre-installed on Windows 11). Flask stays unchanged; pywebview renders the existing HTML/CSS/JS.

**Files to change:** `requirements.txt` (add pywebview), `app/main.py` (move pystray to `run_detached()`, launch pywebview on main thread), `app/tray.py` (replace `webbrowser.open()` with pywebview window show/focus), `app/server.py` (remove `webbrowser.open()` startup call).

**Key constraint:** Both pystray and pywebview require the main thread. Solution: use pystray's `icon.run_detached()` to free the main thread for pywebview.

---

## How to Run

```bash
python -m app.main
```

Exit: tray icon right-click → Quit (Ctrl+C is blocked by pystray).

## Dependencies

```
pyaudiowpatch    # WASAPI loopback audio capture
faster-whisper   # Local transcription
anthropic        # Claude API
keyring          # Windows Credential Manager
flask            # Web UI server
pystray          # System tray icon
Pillow           # Icon image generation
# System: ffmpeg in PATH
```
