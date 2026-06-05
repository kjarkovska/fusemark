# ObsiNote — Product Brief

**Version:** 0.9.2  
**Date:** June 2026

---

## Problem

Existing meeting notes tools (Granola.ai, Otter.ai, etc.) either don't support Czech well, send audio to the cloud, or are too expensive. The goal is a minimal, functional solution that runs locally, understands Czech, and fits naturally into the existing workflow.

---

## What It Is

A local desktop application for Windows 11 that records meeting audio, transcribes it locally, and generates structured notes in Czech directly into an Obsidian vault. Inspired by Granola.ai, tailored for Czech language and personal workflow.

---

## User

Single user (with potential to share with friends). ASUS ExpertBook laptop, Windows 11 Pro, ~8–12 hours of meetings per week (Teams, Zoom, browser-based calls). Frequent use of Bluetooth headset. Frequent back-to-back meetings.

---

## Core Principles

- **Audio never leaves the machine** — only the text transcript is sent to the cloud
- **No real-time transcription** — processing happens in the background, independent of recording
- **Minimal friction** — tray icon, two clicks to start recording
- **Czech-first** — output defaults to Czech; configurable to any language
- **Cheap to run** — cost depends on chosen LLM provider; local transcription is free
- **Shareable** — easy to set up for other users

---

## Architecture

```
Audio capture (WASAPI loopback + mic — separate streams)
        ↓
  .mp3 file (stored locally)
        ↓
  Job Queue (SQLite — persistent)
        ↓
  faster-whisper (configurable model, local, CPU, background)
        ↓
  Transcript + Scratch notes + Context + Glossary
        ↓
  Anthropic / OpenAI / Mistral API (configurable)
        ↓
  .md file → Obsidian vault
        ↓
  New term suggestions → glossary.json (optional)
```

| Layer | Technology |
|---|---|
| Audio capture | Python + `pyaudiowpatch` (WASAPI loopback, separate streams) |
| Transcription | `faster-whisper` (configurable: small / large-v3-turbo / large-v3, local, CPU) |
| Note generation | Anthropic Haiku 4.5 / OpenAI GPT-4o-mini / Mistral Small (configurable) |
| UI | Flask + HTML + `pywebview` (standalone window, no browser needed) |
| System integration | `pystray` (tray icon) |
| Job queue | SQLite (via Python `sqlite3`, WAL mode) |
| API key storage | Windows Credential Manager (via `keyring`) |
| Glossary | `glossary.json` in `%APPDATA%\ObsiNote\` |
| Output | Markdown → Obsidian vault |
| i18n | English / Czech UI (configurable) |

---

## Back-to-Back Meetings — Decoupled Pipeline

Recording and processing are completely decoupled. As soon as recording stops, the audio is saved and the job is queued — the app is immediately ready to record the next meeting.

```
Meeting 1 ends → job saved to SQLite → IMMEDIATELY ready to record
Meeting 2 starts → recording in parallel
Background worker → processes Meeting 1 (Whisper → Claude)
Meeting 2 ends → second job queued
Background worker → processes Meeting 2
```

**Job states:** `recording → queued → transcribing → generating → done / error`

On app restart, the worker automatically resumes interrupted jobs.

---

## Bluetooth Headset

Audio is captured as **two separate streams**:
- System audio — WASAPI loopback from the default output device
- Microphone — separate input stream

This prevents Windows from switching between HSP/HFP and A2DP profiles, which degrades audio quality. Streams are mixed in software. Audio device selection is configurable in settings.

---

## Glossary

File `glossary.json` in the project root, editable in VSCode.

```json
{
  "terms": [
    {
      "canonical": "Jira",
      "aliases": ["Yira", "Džira", "jira"],
      "context": "project management tool",
      "type": "product"
    },
    {
      "canonical": "PR",
      "aliases": ["pé er", "pull request"],
      "context": "git pull request",
      "type": "abbreviation"
    }
  ]
}
```

**Usage:**
- Whisper: canonical terms + aliases → hotwords prompt (better transcription)
- Claude: full structured glossary → system prompt (better notes)

**Auto-suggestions after each meeting:**
- Claude identifies up to 5 unconventional terms from the transcript
- Only terms not found in standard Czech or English dictionaries
- Suggestion includes canonical form and context
- User approves or dismisses in the UI before writing to file
- App opens `glossary.json` in VSCode after approval

---

## User Flow

1. **Click tray icon** → small window opens
2. **Select vault folder** (dropdown from history) + meeting label → date added automatically
3. **Start recording** → icon turns red, timer runs, scratch pad available
4. **During meeting** → optionally jot rough notes in the scratch pad
5. **Stop** → audio saved, job queued, **app immediately ready for next meeting**
6. **Jobs panel** → shows status of all jobs (current + queue + completed)
7. **Context** → add participants, project, meeting goal at any time before processing completes
8. **Audio decision** → Archive `.mp3` / Discard (can be decided after processing too)
9. **Done** → `.md` file in Obsidian vault + optional glossary term suggestions

---

## UI — Screens and Panels

**Tray icon:**
- Grey = idle
- Red (pulsing) = recording
- Right click: Start / Stop / Open / Quit

**Main window — three sections:**

**A) Recorder** (top)
- Timer + meeting label + folder selector
- Scratch pad
- Start / Stop button

**B) Jobs panel** (middle)
- List of jobs with status and progress bar
- Per job: add context, decide on audio
- States: Recording / Queued / Transcribing / Generating / Done / Error

**C) Settings** (accessible via icon)
- Vault path, audio devices
- Whisper model (visual table with download badges)
- LLM provider + API key per provider (test button)
- Language selection (transcription + notes)
- UI language (English / Czech)
- Recording housekeeping (size, auto-delete, max GB)
- Update checker (version display, check-now button)
- Autostart toggle (Windows registry)
- Open glossary in VSCode

**First-run wizard:** 5-step setup (welcome → LLM key → Whisper model download → audio devices → vault folder)

---

## Obsidian Vault Structure

```
Vault/
└── Meetings/
    ├── Projects/
    │   └── ProjectX/
    │       └── 2026-03-10 Kickoff.md
    ├── 1on1/
    │   └── 2026-03-12 Petr.md
    └── Other/
        └── 2026-03-14 Standup.md
```

## Output Note Template

```markdown
---
date: 2026-03-10
type: meeting
tags: [meeting]
---

# Meeting Title

## Participants

## Context

## Summary

## Decisions

## Action Items
- [ ] Task — responsible person

## Notes

---
<details>
<summary>Transcript</summary>

[full transcript here]

</details>
```

---

## Job Queue — Data Model

```sql
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  created_at TEXT,
  updated_at TEXT,
  label TEXT,
  folder TEXT,
  template TEXT,
  meeting_date TEXT,
  recording_path TEXT,
  audio_path TEXT,
  scratch_notes TEXT,
  extra_context TEXT,
  status TEXT,              -- recording/queued/transcribing/generating/done/error
  transcript TEXT,
  transcript_path TEXT,
  output_note_path TEXT,
  glossary_terms TEXT,      -- JSON array of suggested terms
  keep_audio INTEGER,       -- NULL=undecided, 1=keep, 0=delete
  error_message TEXT
);
```

---

## API Key

Stored in **Windows Credential Manager** via Python `keyring`. On first launch the app prompts for the key. The key is never stored in a file or in code. Fully portable — each user has their own key in their own system.

---

## Cost Estimate

| | Monthly |
|---|---|
| faster-whisper (transcription) | $0 — fully local |
| LLM (note generation, ~43h/month) | ~$0.67 with Claude Haiku 4.5; varies by provider |
| **Total** | **$0–~$1/month depending on provider** |

---

## Future Considerations

**Voxtral / EU hosting:** If this project grows toward a multi-user or SaaS deployment, evaluate replacing the Whisper + Claude pipeline with [Voxtral](https://huggingface.co/mistralai/Voxtral-Small-24B-2507) hosted on EU infrastructure. Voxtral (by Mistral AI, a French company) combines transcription and note generation into a single model call, simplifies the pipeline, and falls under EU/GDPR jurisdiction — a meaningful advantage for a meeting notes product handling potentially sensitive business conversations. Requires significant GPU resources (~55GB VRAM for the 24B model). The Mini 3B variant needs ~9.5GB VRAM and could work on modest GPU hardware.

---

## Deliberately OUT of Scope for v1.0

- Live transcription
- Speaker diarization (who said what) — possible future addition
- Mobile access
- Sync or cloud backup
- Packaged installer / distribution — run locally via Python
