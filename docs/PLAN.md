# ObsiNote — Implementation Plan

---

## Project Structure

```
obsinote/
├── BRIEF.md                 # Product brief
├── PLAN.md                  # This file
├── README.md                # Setup and usage instructions
├── requirements.txt         # Python dependencies
├── glossary.json            # Term glossary (editable in VSCode)
├── config.json              # Vault path, audio devices, model size (auto-created)
├── jobs.db                  # SQLite job queue (auto-created)
├── app/
│   ├── main.py              # Entrypoint — launches tray + Flask
│   ├── tray.py              # pystray icon and menu
│   ├── server.py            # Flask web server + routes
│   ├── recorder.py          # Audio capture (WASAPI loopback + mic)
│   ├── worker.py            # Background job processor
│   ├── transcriber.py       # faster-whisper wrapper
│   ├── notemaker.py         # Claude API — notes + glossary suggestions
│   ├── queue.py             # SQLite job queue CRUD
│   ├── config.py            # Load and save configuration
│   └── glossary.py          # Load glossary, handle suggestions
├── templates/
│   ├── index.html           # Main UI
│   └── settings.html        # Settings screen
└── static/
    ├── style.css
    └── app.js
```

---

## Phase 1 — Project Skeleton & Audio Capture

**Goal:** Working recording with correct audio mix (system + mic)

### Tasks
- Set up project structure, `requirements.txt`, basic `config.py`
- `recorder.py` — WASAPI loopback (system audio) as a separate stream
- `recorder.py` — microphone as a separate stream
- Software mix of both streams, save as `.mp3`
- Audio device detection and selection (important for BT headset)
- Basic CLI test of recording without UI

### Test
```bash
python app/recorder.py --test
# Should create a test.mp3 in the project root
# Play it back and verify both system audio and mic are captured
```

### Key Dependencies
```
sounddevice
numpy
pydub
```
(ffmpeg required as system dependency — must be in PATH)

### Risk
Bluetooth headset — requires real testing on target hardware. Windows may switch audio profiles. Verify that capturing WASAPI loopback and mic as separate streams prevents profile switching.

---

## Phase 2 — Job Queue & Worker

**Goal:** Persistent queue that survives app restarts

### Tasks
- `queue.py` — SQLite schema, CRUD operations for jobs
- State machine: `recording → queued → transcribing → generating → done / error`
- `worker.py` — background thread, processes jobs one at a time
- Recovery on startup — jobs stuck in `transcribing` or `generating` → reset to `queued`
- Basic CLI test of queue operations

### Test
```bash
python app/queue.py --test
# Should create a test job, transition through states, and mark as done
# Restart and verify the job is still there
```

### Key Dependencies
```
sqlite3  (built-in, no install needed)
```

### SQLite Schema
```sql
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  created_at TEXT,
  label TEXT,
  folder TEXT,
  recording_path TEXT,
  audio_path TEXT,
  scratch_notes TEXT,
  extra_context TEXT,
  status TEXT,
  transcript TEXT,
  output_note_path TEXT,
  keep_audio INTEGER,
  error_message TEXT,
  updated_at TEXT
);
```

---

## Phase 3 — Transcription

**Goal:** Working Whisper pipeline with glossary support

### Tasks
- `transcriber.py` — faster-whisper wrapper, model `large-v3`
- Glossary integration as hotwords / initial prompt for Whisper
- Progress reporting back to the job record in SQLite
- Remaining time estimate (calibrate on CPU)
- Test on a real Czech audio recording

### Test
```bash
python app/transcriber.py --file test.mp3
# Should print the transcript to console
# Verify Czech words are correctly transcribed
# Verify glossary terms are respected
```

### Key Dependencies
```
faster-whisper
```

### Notes
- First run downloads the model (~3GB) — README must warn about this
- `large-v3` is recommended for Czech quality; `medium` is a fallback for low-RAM situations
- Expected transcription speed on CPU (Intel i7): roughly 10–15 min per 1h of audio

---

## Phase 4 — Note Generation

**Goal:** Claude Haiku 3.5 produces structured Czech notes

### Tasks
- `keyring` setup — store and retrieve API key from Windows Credential Manager
- `notemaker.py` — build system prompt (glossary, output template, Czech instructions)
- Build user prompt — transcript + scratch notes + extra context
- Parse output → write `.md` file to correct vault folder
- Second Claude pass — suggest up to 5 new glossary terms
- `glossary.py` — add approved terms to file, open in VSCode

### Test
```bash
python app/notemaker.py --transcript test_transcript.txt
# Should create a .md file in the configured vault folder
# Verify Czech output, correct structure, glossary terms used correctly
# Verify glossary suggestions are reasonable
```

### Key Dependencies
```
anthropic
keyring
```

### Claude System Prompt Structure
```
You are a meeting notes assistant. You write in Czech.
You will receive a transcript, scratch notes, and context.
Generate structured meeting notes using the provided template.
Glossary of domain terms: [glossary JSON]
Output template: [markdown template]
Instructions: Always write in Czech. Use the glossary for proper term spelling.
Action items must be formatted as checkboxes.
```

---

## Phase 5 — UI & Tray

**Goal:** Usable window + tray icon

### Tasks
- `tray.py` — pystray icon, states (idle/recording), right-click menu
- `server.py` — Flask app, routes for recorder control and job management
- `index.html` — three sections: Recorder, Jobs panel, Settings link
- Recorder section: timer, label field, folder dropdown, scratch pad, start/stop button
- Jobs panel: job list with status, progress bar, context field, audio decision
- `settings.html` — vault path, audio devices, Whisper model, API key, glossary button
- `main.py` — launches Flask in a thread, opens browser, starts tray icon

### Test
- Launch `python app/main.py`
- Verify tray icon appears
- Verify browser opens to UI
- Verify start/stop recording works from UI
- Verify jobs appear in the panel after stopping

### Key Dependencies
```
flask
pystray
Pillow
```

---

## Phase 6 — Integration & Polish

**Goal:** Everything works end-to-end, ready for daily use

### Tasks
- Full end-to-end test (recording → vault note)
- Back-to-back meeting test (start new recording immediately after stopping previous)
- Bluetooth headset test (real conditions)
- Error handling:
  - Whisper fails → job marked as error, audio preserved
  - Claude API unavailable → retry logic, job stays in queue
  - Vault folder doesn't exist → create it automatically
- Auto-start with Windows (optional, toggle in settings)
- Final `README.md` — complete setup instructions

### Final End-to-End Test Checklist
- [ ] Record a 5-minute test meeting
- [ ] Stop recording — verify job appears in queue
- [ ] Start a second recording immediately — verify app doesn't block
- [ ] Wait for transcription — verify Czech transcript quality
- [ ] Generate notes — verify `.md` file appears in Obsidian vault
- [ ] Check note structure matches template
- [ ] Verify glossary suggestions appear (if applicable)
- [ ] Test with Bluetooth headset connected

---

## requirements.txt

```
flask
faster-whisper
sounddevice
numpy
pydub
anthropic
keyring
pystray
Pillow
```

---

## README — Key Sections

1. **Requirements** — Python 3.11+, ffmpeg in PATH, Windows 11
2. **Installation** — clone repo, `pip install -r requirements.txt`
3. **First launch** — enter API key, set vault path, Whisper model download (~3GB)
4. **Audio device configuration** — especially for Bluetooth headset
5. **Glossary** — how to edit `glossary.json`, structure explanation
6. **Daily use** — tray icon, recording flow, jobs panel
7. **Troubleshooting** — common issues and fixes

---

## Recommended Approach for Claude Code

Work phase by phase. Each phase ends with a working, testable state before moving to the next. **Phase 1 (audio capture) is the highest risk** — give it the most attention and test on real hardware before continuing. If faster-whisper has issues with Python 3.13, fall back to Python 3.11 or 3.12 for this project using a virtual environment.

### Starting a Claude Code session
Always begin by saying:
> "Read BRIEF.md and PLAN.md. We are working on Phase X — [phase goal]."

### After each phase
```bash
git add .
git commit -m "Phase X - [description] complete"
```
