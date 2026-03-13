# Granola-CZ

Local meeting notes app for Windows 11. Records audio, transcribes with faster-whisper, generates structured Czech notes via Claude Haiku API, saves to Obsidian vault.

**Audio never leaves your machine.** Only the text transcript is sent to the Claude API.

---

## Requirements

- Windows 11
- Python 3.11+ (tested on 3.13)
- [ffmpeg](https://ffmpeg.org/download.html) — must be in PATH
- Anthropic API key — [console.anthropic.com](https://console.anthropic.com)
- Obsidian vault (optional for testing, required for daily use)

---

## Installation

```bash
git clone https://github.com/kjarkovska/note-taker.git
cd note-taker
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

Verify ffmpeg is in PATH:
```bash
ffmpeg -version
```

---

## First Launch

```bash
venv\Scripts\python -m app.main
```

A browser opens at `http://127.0.0.1:5000` and a tray icon appears.

**Settings to configure on first run:**

1. **Vault path** — full path to your Obsidian vault root (e.g. `C:\Users\You\Documents\Obsidian\MyVault`)
2. **API key** — paste your Anthropic API key; stored in Windows Credential Manager, never in files
3. **Whisper model** — `small` is fast and good enough for most meetings; `large-v3` gives better quality but requires a ~3 GB download on first use
4. **Audio devices** — defaults work for built-in speakers/mic; change if using a specific device

---

## Daily Use

1. Click the tray icon → **Start Recording** (or use the Start button in the browser UI)
2. The timer runs; jot rough notes in the scratch pad if useful
3. Click **Stop Recording** — audio is saved and the job is queued immediately
4. The app is ready to record the next meeting right away
5. Transcription and note generation happen in the background
6. When done, the note appears in `<vault>/Meetings/<folder>/<date> <label>.md`
7. Review glossary term suggestions in the jobs panel if any appear

**Exit:** tray icon right-click → **Quit**

---

## Audio Device Configuration

### Built-in speakers + mic
No configuration needed — defaults work.

### Bluetooth headset (e.g. JBL)
Windows switches the headset to HSP/HFP (lower quality call mode) when the mic is active — this is a Windows OS limitation and cannot be avoided. The recording quality is still sufficient for transcription.

To use the BT headset mic instead of the built-in mic:
1. Open Settings in the app
2. Set **Input device** to your headset mic (e.g. `Headset (JBL LIVE650BTNC)`)
3. Leave **Output device** as default — the loopback is auto-detected

---

## Glossary

Edit `glossary.json` in the project root to add domain-specific terms. The app uses it to:
- Improve Whisper transcription accuracy (canonical forms + aliases as hotwords)
- Guide Claude to use correct spelling in generated notes

After each meeting, Claude suggests up to 5 new terms found in the transcript. Review them in the jobs panel and add the ones you want.

**Structure:**
```json
{
  "terms": [
    {
      "canonical": "Jira",
      "aliases": ["Yira", "Džira"],
      "context": "project management tool",
      "type": "product"
    }
  ]
}
```

---

## Output Note Structure

Notes are saved to `<vault>/Meetings/<folder>/<date> <label>.md`:

```markdown
---
date: 2026-03-13
type: meeting
tags: [meeting]
---

# 2026-03-13 Meeting Title

## Participants
## Context
## Summary
## Decisions
## Action Items
- [ ] Task — responsible person
## Notes

<details><summary>Transcript</summary>
[full transcript]
</details>
```

---

## Troubleshooting

**App won't start / tray icon missing**
- Make sure you're running from the project root: `venv\Scripts\python -m app.main`

**No audio in recording**
- Check that ffmpeg is in PATH: `ffmpeg -version`
- In Settings, verify the correct output and input devices are selected
- Run `venv\Scripts\python -m app.recorder --list-devices` to see all device indices

**Transcription is slow**
- Expected: ~10–15 min per hour of audio on CPU with `large-v3`; `small` is much faster
- First run with a new model downloads it from HuggingFace (~500 MB for small, ~3 GB for large-v3)

**Note not appearing in vault**
- Check that vault path is set correctly in Settings
- Check the jobs panel — if status is `error`, read the error message

**API key error**
- Go to Settings, paste key again and save
- The key is stored in Windows Credential Manager under `granola-cz`

**Ctrl+C doesn't stop the app**
- Use tray icon → Quit, or: `taskkill /f /im python.exe`
