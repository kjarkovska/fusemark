# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Project

**Granola-CZ** — a local Windows 11 desktop app for recording meeting audio, transcribing it locally with faster-whisper, and generating structured Czech meeting notes into an Obsidian vault via Claude Haiku 3.5 API.

Audio never leaves the machine. Recording and processing are fully decoupled so back-to-back meetings work seamlessly.

## Documentation

All project documentation lives in the [`docs/`](docs/) folder:

- [`docs/BRIEF.md`](docs/BRIEF.md) — Product brief: goals, architecture, user flow, UI design, data model, cost estimate, and out-of-scope items.
- [`docs/PLAN.md`](docs/PLAN.md) — Implementation plan: phased build order (Phase 1–6), project file structure, per-phase tasks and test commands, and recommendations for working with Claude Code.

**Always read both files at the start of a session before making any changes.**

## How to Work on This Project

The plan is phase-based. Start each session by stating which phase you are on:

> "Read BRIEF.md and PLAN.md. We are working on Phase X — [phase goal]."

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

- Python 3.11+ (fall back to 3.11/3.12 if faster-whisper has issues with 3.13)
- ffmpeg must be in PATH
- Windows 11 only (WASAPI loopback)
- API key stored in Windows Credential Manager — never in files or code
