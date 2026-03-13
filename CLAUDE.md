# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Project

**Granola-CZ** — a local Windows 11 desktop app for recording meeting audio, transcribing it locally with faster-whisper, and generating structured Czech meeting notes into an Obsidian vault via Claude Haiku 3.5 API.

Audio never leaves the machine. Recording and processing are fully decoupled so back-to-back meetings work seamlessly.

## Current Status

**Phase 4 — complete. Ready to start Phase 5.**

- `app/recorder.py` — dual-stream capture (WASAPI loopback + mic) via `pyaudiowpatch`; ffmpeg mixes to mp3
- `app/config.py` — load/save `config.json`
- `app/queue.py` — SQLite job queue, full CRUD, state machine, startup recovery
- `app/worker.py` — fully wired: transcribe -> generate -> save note, glossary suggestions stored in job
- `app/transcriber.py` — faster-whisper wrapper, Czech forced, glossary initial_prompt, progress reporting to SQLite
- `app/glossary.py` — load glossary.json, build Whisper prompt, add terms, open in VSCode
- `app/notemaker.py` — Claude Haiku 3.5: generates Czech notes, suggests glossary terms; API key via keyring
- Run all modules with `python -m app.X` (not `python app/X.py`) — avoids import errors
- Reading transcript files: use `errors='replace'` — terminal redirects write CP1250, not UTF-8
- Currently using `small` Whisper model — sufficient in initial test; upgrade to large-v3 if quality is lacking
- BT note: Windows switches JBL to HSP/HFP when mic opens. Windows OS limitation — unavoidable. Acceptable for transcription quality.

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