# FuseMark

Local meeting notes app for Windows 11. Records audio, transcribes locally with faster-whisper, generates structured notes via your choice of LLM API, saves to an Obsidian vault (or any folder).

**Audio never leaves your machine.** Only the text transcript is sent to the LLM API.

---

## Get FuseMark

FuseMark is **free and open-source** (GPL v3). Clone the repo and run from source — no installer needed.

If FuseMark saves you time, consider [sponsoring on GitHub](https://github.com/sponsors/kjarkovska) ☕

The source is licensed under **GPL v3** — see [License](#license).

---

## Requirements

- Windows 11
- Python 3.11+ (tested on 3.13)
- [ffmpeg](https://ffmpeg.org/download.html) — must be in PATH
- API key for one of: Anthropic Claude, OpenAI, or Mistral
- Obsidian vault (optional for testing, required for daily use)

---

## Installation

```bash
git clone https://github.com/kjarkovska/fusemark.git
cd fusemark
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

A native app window opens. On first run a setup wizard guides you through:

1. **LLM provider** — choose Anthropic Claude, OpenAI, or Mistral; enter and test your API key
2. **Whisper model** — download `large-v3-turbo` (recommended, 1.5 GB) or `large-v3` (3.1 GB, highest accuracy)
3. **Audio devices** — test a 5-second recording to verify your mic and system audio capture work
4. **Output folder** — full path to your Obsidian vault root (or any folder for Markdown output)

API keys are stored in Windows Credential Manager — never in files or config.

---

## Daily Use

1. Enter a meeting name and folder, then click **Start recording**
2. Jot quick notes in the scratch pad during the meeting if useful
3. Click **Stop recording** — audio is saved and the job is queued immediately
4. The app is ready to record the next meeting right away
5. Transcription and note generation happen in the background
6. When done, the note appears in `<vault>/FuseMark/Meetings/<folder>/<date> <label>.md`
7. Review glossary term suggestions in the jobs panel if any appear

**Import without recording:** use **Import transcript** to paste or upload a `.txt`/`.md`/`.vtt` transcript, or **Import audio** to process an existing `.mp3`/`.wav`/`.m4a`/`.ogg`/`.flac` file.

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

The glossary lives at `<vault>/FuseMark/Glossary.md` as a Markdown table (falls back to `%APPDATA%\FuseMark\` if no vault is configured). The app uses it to:
- Improve Whisper transcription accuracy (canonical forms + aliases as hotwords)
- Guide the LLM to use correct spelling in generated notes

After each meeting, the LLM suggests up to 5 new terms found in the transcript. Review them in the jobs panel and add the ones you want. You can also open `Glossary.md` directly in Obsidian from Settings → Glossary.


---

## Output Note Structure

Notes are saved to `<vault>/FuseMark/Meetings/<folder>/<date> <label>.md`:

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
```

The raw transcript is saved separately to `<vault>/FuseMark/Transcripts/<date> <label>.md`.

### Custom templates

Place a `.md` file in `<vault>/FuseMark/Templates/` and select it in Settings → Default template. The template is passed to the LLM as the output structure — use any headings you like. If no custom template is selected, the built-in structure above is used.

---

## Data Storage

App data in `%APPDATA%\FuseMark\`:

```
%APPDATA%\FuseMark\
├── config.json       — app settings
├── jobs.db           — processing queue
├── logs\fusemark.log
└── recordings\       — .mp3 files (auto-deleted after processing if configured)
```

Vault data in `<vault>/FuseMark/`:

```
<vault>/FuseMark/
├── Meetings\         — generated notes (<date> <label>.md)
├── Transcripts\      — raw transcripts (<date> <label>.md)
├── Templates\        — custom note templates (optional, .md files)
└── Glossary.md       — term list used by Whisper and the LLM
```

The glossary falls back to `%APPDATA%\FuseMark\Glossary.md` if no vault is configured.

Whisper models are stored in `%LOCALAPPDATA%\FuseMark\models\` (local disk, not a network path).

---

## Troubleshooting

**App won't start / tray icon missing**
- Make sure you're running from the project root: `venv\Scripts\python -m app.main`

**No audio in recording**
- Check that ffmpeg is in PATH: `ffmpeg -version`
- In Settings, verify the correct output and input devices are selected
- Run `venv\Scripts\python -m app.recorder --list-devices` to see all device indices

**Transcription is slow**
- Expected: ~10–15 min per hour of audio on CPU with `large-v3`; `large-v3-turbo` is ~6× faster with near-identical quality
- First run with a new model downloads it from HuggingFace (1.5 GB for turbo, 3.1 GB for large-v3)

**Whisper model not downloaded error**
- Go to Settings → Whisper model and click Download

**Note not appearing in vault**
- Check that the output folder is set correctly in Settings
- Check the jobs panel — if status is `error`, read the error message

**API key error**
- Go to Settings, enter your key and click Save key
- Keys are stored in Windows Credential Manager under `FuseMark-Anthropic`, `FuseMark-OpenAI`, or `FuseMark-Mistral`

**Ctrl+C doesn't stop the app**
- Use tray icon → Quit, or: `taskkill /f /im python.exe`

---

## Privacy

Audio is processed entirely on your machine and is never uploaded. Only the text
transcript and any notes/context you type are sent to your chosen LLM provider to
generate the meeting note. API keys are stored in Windows Credential Manager. See
[docs/PRIVACY_POLICY.md](docs/PRIVACY_POLICY.md) for full details.

---

## License

FuseMark is free software under the **GNU General Public License v3.0** — see
[LICENSE](LICENSE). You may use, study, modify, and redistribute it. If you
distribute it (as source or as a binary), you must make the complete corresponding
source available under GPL v3.

---

## Credits

FuseMark is built on top of excellent open-source work:

- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** — CTranslate2-based Whisper inference (Systran); turbo variant by [mobiuslabsgmbh](https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo)
- **[PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)** — WASAPI loopback capture on Windows
- **[pystray](https://github.com/moses-palmer/pystray)** — system tray icon
- **[pywebview](https://pywebview.flowrl.com/)** — native app window and folder picker dialog
- **[Flask](https://flask.palletsprojects.com/)** — local web UI
- **[Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python)**, **[OpenAI Python SDK](https://github.com/openai/openai-python)**, **[Mistral Python client](https://github.com/mistralai/client-python)** — LLM provider integrations
- **[keyring](https://github.com/jaraco/keyring)** — Windows Credential Manager API key storage
- **[PyInstaller](https://pyinstaller.org/)** — app packaging
- **[ffmpeg](https://ffmpeg.org/)** — audio mixing and encoding
