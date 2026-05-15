# ObsiNote — Production Roadmap Plan
**Target:** Shippable v1.0 for general public, open-source code + paid installer, Windows 10/11

> This document is written for Claude Code. Read it fully before starting any phase.
> Each phase ends with a testable, stable state. Never start a new phase on top of broken code.
> Run `python -m app.main` to verify the app still launches correctly after every significant change.

---

## ⚠ Before Starting — Name Trademark Risk

**"ObsiNote" is too close to "Obsidian" (Dynalist Inc.) to use publicly.** Obsidian is a
registered brand in exactly the target market — users who want to save Markdown notes into
an Obsidian vault. The name sounds like a portmanteau of "Obsidian" + "Note" and will cause
user confusion and potential trademark claims.

**Choose a different product name before any public announcement, Gumroad listing, or
code signing.** The app's functionality is completely independent of Obsidian (it writes
plain Markdown files). The name should reflect the recording/transcription/notes angle, not
the Obsidian integration. Throughout this document "ObsiNote" is used as a placeholder only.

---

## Distribution Model

The source code is **GPL v3-licensed and publicly available on GitHub**. Anyone can clone the
repo and run the app for free.

The **Gumroad listing sells a pre-compiled Windows installer** as a convenience product
(~€19, one-time). Buyers get a signed `.exe` that works immediately — no Python environment,
no build toolchain, no dependency management. The value is the packaging and setup work,
not access to the code.

**GPL v3 copyleft implications:** anyone who distributes the source code or a compiled
binary — including the Gumroad installer — must also make the complete corresponding source
available under GPL v3. This is satisfied by linking to the public GitHub repo from the
Gumroad product page. It also prevents competitors from taking the code, compiling it, and
selling a closed binary without releasing their source.

**The `LICENSE` file containing the full GPL v3 text must be committed to the repository
root before the first public commit.** The repo must never be made public without it.

Implications for the plan:
- No license key validation, no trial period, no paywall mechanics anywhere in the app.
- `main.py` does not call any license check on startup.
- The Settings UI has no license section.
- Gumroad is configured as a simple file download — license key generation is disabled.
- A `LICENSE` file (GPL v3) lives at the repo root and is displayed during install.

---

## Overview of Changes from MVP

The MVP is a single-user, Czech-only, Whisper-only tool running from source.
Production v1.0 adds:

1. **Dual pipeline mode** — Private (local Whisper) and Cloud (remote STT API)
2. **Pluggable LLM providers** — Claude, OpenAI, Mistral (same abstraction for both STT and LLM)
3. **Language selection** — any Whisper-supported language, not hardcoded Czech
4. **Data stored in `%APPDATA%`** — not the install directory
5. **First-run onboarding wizard** — mode selection, API key, audio device, output folder
6. **Visible, mode-specific error UX** — no silent failures
7. **Single `.exe` installer** — PyInstaller + Inno Setup, ffmpeg bundled
8. **Update notifications** — check GitHub releases, show banner in UI
9. **Recording housekeeping** — size display, auto-cleanup option
10. **Gumroad listing** — paid pre-compiled installer for convenience; source code is GPL v3-licensed
11. **UI language (Czech / English)** — all user-facing strings switchable; English is the default for new installs (P5.5)
12. **Audio file import** — dedicated "Import audio" button and modal; uploads `.mp3`/`.wav`/`.m4a`/`.ogg`/`.flac` for transcription + note generation; optional scratch notes attached; complete as of 2026-05-15

The existing pipeline architecture (recorder → queue → worker → notemaker) is preserved.
The existing Flask + pywebview UI shell is preserved.
Changes are additive and modular — each module gets a clean interface, implementations swap behind it.

---

## File Structure After All Phases

```
obsinote/
├── app/
│   ├── main.py                  # unchanged except %APPDATA% paths + port selection
│   ├── server.py                # new routes: /setup, /wizard, /update-check, /recordings/cleanup
│   ├── recorder.py              # unchanged except ffmpeg_exe() import from app.utils
│   ├── worker.py                # calls transcribe() and generate() via provider interfaces
│   ├── queue.py                 # unchanged
│   ├── config.py                # extended: mode, language, providers, model dir
│   ├── autostart.py             # updated: launch path from %APPDATA%, not project root
│   ├── tray.py                  # unchanged
│   ├── glossary.py              # unchanged
│   ├── updater.py               # NEW: GitHub release check
│   ├── notes.py                 # NEW: save_note() and save_transcript() file-writing utilities
│   ├── exceptions.py            # NEW: shared custom exception classes
│   ├── utils.py                 # NEW: ffmpeg_exe() and other cross-cutting utilities
│   ├── i18n.py                  # NEW (P5.5): TRANSLATIONS dict + get_strings(); "en" default
│   ├── transcription/
│   │   ├── __init__.py          # transcribe() dispatcher
│   │   └── local.py             # faster-whisper (moved from transcriber.py)
│   └── llm/
│       ├── __init__.py          # generate_notes() and suggest_glossary_terms() dispatchers
│       ├── anthropic_provider.py # Claude (moved from notemaker.py)
│       ├── openai_provider.py   # GPT-4o-mini
│       └── mistral_provider.py  # Mistral small
├── templates/
│   ├── index.html               # unchanged core; update banner added
│   ├── settings.html            # extended: mode, language, providers, housekeeping
│   └── wizard.html              # NEW: first-run setup wizard (5 steps)
├── static/
│   ├── style.css                # minor additions for wizard and error states
│   └── app.js                   # unchanged core; wizard flow + update banner JS added
├── installer/
│   ├── build.spec               # PyInstaller spec
│   ├── setup.iss                # Inno Setup script
│   └── ffmpeg/                  # bundled ffmpeg binary (place here before build)
├── assets/                      # unchanged
├── docs/
│   ├── PRODUCTION_PLAN.md       # this file
│   └── PRIVACY_POLICY.md        # NEW in P12: end-user privacy policy
├── LICENSE                      # GPL v3 License (root of repo)
├── requirements.txt             # updated
└── CLAUDE.md                    # updated after each phase
```

---

## Data & Config Location

**All user data moves to `%APPDATA%\ObsiNote\`** — the install directory is read-only on most machines.

```
%APPDATA%\ObsiNote\
├── config.json       # all settings
├── glossary.json     # user's glossary
├── jobs.db           # SQLite queue
├── logs\
│   └── obsinote.log
└── recordings\       # .mp3 files (if not auto-deleted)
```

`config.py` must export a `DATA_DIR` constant:
```python
DATA_DIR = os.path.join(os.environ["APPDATA"], "ObsiNote")
```
All modules that currently reference `PROJECT_ROOT` for data files must switch to `DATA_DIR`.
The install directory itself contains only code, assets, and ffmpeg.

---

## Extended `config.json` Schema

```json
{
  "mode": "private",
  "transcription_provider": "whisper_local",
  "llm_provider": "anthropic",
  "language": "cs",
  "language_name": "Czech",
  "whisper_model": "large-v3-turbo",
  "whisper_model_dir": "%LOCALAPPDATA%\\ObsiNote\\models",
  "vault_path": "",
  "output_device": null,
  "input_device": null,
  "log_level": "INFO",
  "default_template": "",
  "auto_delete_recordings": false,
  "max_recordings_gb": 5.0,
  "check_updates": true,
  "setup_complete": false,
  "ui_language": "en",
  "last_update_check": null,
  "latest_known_version": null
}
```

`last_update_check` and `latest_known_version` are written at runtime by `updater.py` and are
not part of `DEFAULTS` in `config.py`. They appear in `config.json` only after the first
update check runs — do not initialise them in the defaults dict.

The `whisper_model_dir` value shown above (`%LOCALAPPDATA%\\ObsiNote\\models`) is illustrative.
The actual value stored in `config.json` is the expanded path computed at init time, e.g.
`C:\Users\KJ\AppData\Local\ObsiNote\models`. Config loading never expands environment variables
— Python expands them once when building the default and writes the resolved path.

Valid `transcription_provider` values: `"whisper_local"` only in v1.0. `"openai_whisper"` is
reserved for cloud mode in v1.1 — define it in the dispatcher's `ValueError` branch so a
misconfigured value fails loudly rather than silently.
Valid `llm_provider` values: `"anthropic"`, `"openai"`, `"mistral"`
Valid `mode` values: `"private"` only in v1.0. `"cloud"` is reserved for v1.1. Keep the
field in config now so v1.1 users need no migration.

`setup_complete: false` triggers the wizard on next launch.

`whisper_model_dir` defaults to `%LOCALAPPDATA%\ObsiNote\models` — `%LOCALAPPDATA%` is always
a local disk path even on domain-joined machines where `%APPDATA%` may be redirected to a
network share. Never use `%USERPROFILE%\.cache\huggingface` as the default.

Note on Deepgram: `"deepgram"` is explicitly out of scope for v1.0. The dispatcher must raise
`ValueError(f"Unknown transcription_provider: {provider}")` for any unrecognized value.

---

## Provider Interface Contracts

### Transcription

```python
# app/transcription/__init__.py
def transcribe(audio_path: str, job_id: str | None = None) -> str:
    """Dispatch to the configured transcription provider. Returns full transcript string."""
```

All providers must implement:
```python
def transcribe(audio_path: str, language: str, job_id: str | None, glossary_prompt: str) -> str
```

Progress reporting writes to SQLite via `q.update_job(job_id, extra_context=...)`. Only
`local.py` implements progress in v1.0. Cloud provider progress strings
(`"transcribing:uploading"`, `"transcribing:processing"`) are reserved for v1.1.

### LLM / Note Generation

```python
# app/llm/__init__.py
def generate_notes(transcript: str, label: str, folder: str,
                   scratch_notes: str, extra_context: str, language: str) -> str:
    """Dispatch to the configured LLM provider. Returns markdown note string."""

def suggest_glossary_terms(transcript: str) -> list[dict]:
    """Dispatch to the configured LLM provider. Returns list of term dicts."""
```

All providers must implement both functions with identical signatures.
`language` is passed as a natural-language string (e.g., `"Czech"`, `"English"`) for use in the prompt.

**LLM providers return strings only. File I/O is never the provider's responsibility.**
`save_note()` and `save_transcript()` live in `app/notes.py` and are called by the worker after
`generate_notes()` returns. This keeps provider code testable without touching the filesystem.

### File-writing utilities

```python
# app/notes.py  (moved verbatim from notemaker.py — no logic changes)
def save_note(note: str, label: str, folder: str, vault_path: str, date_str: str) -> str:
    """Write note markdown to vault. Returns output path."""

def save_transcript(transcript: str, label: str, vault_path: str, date_str: str) -> str | None:
    """Write transcript to vault. Returns path or None."""
```

---

## Shared Utilities Created in Early Phases

### `app/exceptions.py` (created in P2, first task)

```python
class ModelNotReadyError(Exception):
    """Raised when the Whisper model has not been downloaded yet."""

class TranscriptionAPIError(Exception):
    """Raised on HTTP errors from cloud transcription providers."""

class LLMRateLimitError(Exception):
    """Raised when the LLM provider returns a rate-limit response."""

class LLMAuthError(Exception):
    """Raised when the LLM provider rejects the API key."""
```

All providers import from `app.exceptions`. Worker imports from `app.exceptions` and catches
these instead of provider-specific exception classes like `anthropic.RateLimitError`.

### `app/utils.py` (created in P2, alongside exceptions.py)

```python
import os, sys

def ffmpeg_exe() -> str:
    """Return the correct ffmpeg executable path for the current runtime."""
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe")
    return "ffmpeg"
```

Every module that invokes ffmpeg as a subprocess calls `ffmpeg_exe()` instead of `"ffmpeg"`.
This centralises the `sys.frozen` detection so P11 needs no per-module changes.

### `app/config.py` additions (created in P1)

```python
WHISPER_MODEL_SIZES = {
    "large-v3-turbo": {"params": "809M", "disk_mb": 1500},
    "large-v3":       {"params": "1.5B",  "disk_mb": 3100},
}
```

Used by the Settings UI to display a static size table — never compute model size dynamically
by inspecting the HuggingFace cache directory, which varies by `HF_HOME`.

---

## ✅ Phase P1 — Data Directory & Config Migration — DONE

**Goal:** All user data reads/writes from `%APPDATA%\ObsiNote\`. App must still launch and work.

**Completed:** 2026-05-07. All user data (config, DB, logs, recordings) reads/writes from
`%APPDATA%\ObsiNote\`. `whisper_model_dir` defaults to `%LOCALAPPDATA%\ObsiNote\models`.
`glossary_terms` column added to jobs DB. Flask runs with `threaded=True`. Tests: 88 passed.

**Why first:** Every subsequent phase touches config or data paths. Getting this right now prevents double-fixing later.

### Tasks

- Add `DATA_DIR` constant to `config.py`
- Add `WHISPER_MODEL_SIZES` dict to `config.py` (used by Settings UI in P7)
- `config.py` load/save: use `DATA_DIR/config.json`
- `config.py` defaults: add `whisper_model_dir` defaulting to
  `os.path.join(os.environ.get("LOCALAPPDATA", DATA_DIR), "ObsiNote", "models")`
- `queue.py`: switch `DB_PATH` to `DATA_DIR/jobs.db`. Extend `init_db()` to migrate all
  columns that will be added in future phases so each later phase does not need to touch
  `init_db()` again. Columns to add if missing (beyond what already exists):
  `error_message TEXT`, `keep_audio INTEGER DEFAULT 0`, `glossary_terms TEXT`.
  Use the existing `PRAGMA table_info` pattern already in the file.

  > **Why `glossary_terms` now:** The current codebase stores glossary suggestions in the
  > `error_message` field (worker.py line 177). This causes every successfully-processed job
  > to display a JSON blob in the red error callout added in P5. Fix it in P1 so the column
  > exists before P3 touches the worker, and update the worker in P3 to write to
  > `glossary_terms` instead of `error_message`.

- `glossary.py`: use `DATA_DIR/glossary.json` — copy existing `glossary.json` from project
  root if found and the `DATA_DIR` version doesn't exist yet (one-time silent migration)
- `main.py` logging: use `DATA_DIR/logs/obsinote.log`
- `recorder.py`: use `DATA_DIR/recordings/` for `.mp3` files
- `server.py`: add `threaded=True` to the `app.run()` call:
  ```python
  def run(port=5000):
      app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False, threaded=True)
  ```
  This is required for SSE streaming (model download progress in P6) — without it, a
  long-lived SSE response blocks all other Flask requests, making the UI unresponsive during
  the entire model download. Add this in P1 so all subsequent phases build on a threaded server.
- `autostart.py`: update VBS launcher to use the installed `.exe` path (not
  `pythonw.exe -m app.main`) — leave a TODO comment for Phase P11, since the actual `.exe`
  path is only known after packaging

### Test

```bash
python -m app.main
# Verify %APPDATA%\ObsiNote\ directory is created on first launch
# Verify config.json, jobs.db appear there
# Record a short clip — verify .mp3 appears in %APPDATA%\ObsiNote\recordings\
# Check logs\obsinote.log exists
# Verify jobs.db has glossary_terms column: sqlite3 jobs.db "PRAGMA table_info(jobs);"
```

### Key constraints

- Never use `PROJECT_ROOT` for any data file after this phase
- `PROJECT_ROOT` is still valid for: `assets/`, `templates/`, `static/`, `app/`
- The `glossary.json` migration must be silent and one-time — no user prompt needed
- `threaded=True` must never be removed — SSE depends on it

---

## ✅ Phase P2 — Provider Abstraction: Transcription — DONE

**Goal:** `transcriber.py` becomes `app/transcription/local.py` behind a clean interface. Worker calls the interface, not the module directly.

**Completed:** 2026-05-07. `app/exceptions.py` (4 exception classes) and `app/utils.py`
(`ffmpeg_exe()`) created. `app/transcription/` package created: `local.py` holds
`transcribe_local(audio_path, language, job_id, glossary_prompt)` with `ModelNotReadyError`
guard; `__init__.py` holds the `transcribe(audio_path, job_id)` dispatcher. `recorder.py`
uses `ffmpeg_exe()`. Worker imports `transcribe` from `app.transcription` and catches
`ModelNotReadyError` separately for a clean error message. `transcriber.py` kept as-is
(legacy CLI only — not imported by any production code). Tests: 88 passed.

### Tasks

**Before writing any provider code — create shared infrastructure:**

- Create `app/exceptions.py` with `ModelNotReadyError`, `TranscriptionAPIError`,
  `LLMRateLimitError`, `LLMAuthError` as shown in the Shared Utilities section above.
  All four classes in one file. All providers and the worker import from here.
  Note: `TranscriptionAPIError` is defined here but unused until v1.1 (cloud transcription).
  Define it now so the v1.1 cloud provider has a ready home for it.

- Create `app/utils.py` with `ffmpeg_exe()` as shown in the Shared Utilities section above.
  Update `recorder.py` to replace `"ffmpeg"` with `ffmpeg_exe()` from `app.utils`.

**Then create the transcription package:**

- Create `app/transcription/` package
- Move `transcriber.py` logic → `app/transcription/local.py`
  - Rename function: `transcribe_local(audio_path, language, job_id, glossary_prompt) -> str`
  - Remove hardcoded `language="cs"` — use the `language` parameter
  - `initial_prompt` (glossary) passed in as parameter, not fetched inside
  - Pass `download_root=config.get("whisper_model_dir")` to `WhisperModel()` so the model
    is stored in `%LOCALAPPDATA%\ObsiNote\models` rather than the HuggingFace default cache
  - Raise `ModelNotReadyError` (from `app.exceptions`) with message
    `"Whisper model not downloaded — go to Settings to download it."` if the model is absent
- **`app/transcription/cloud.py` is out of scope for v1.0** — cloud transcription (OpenAI
  Whisper API) is planned for v1.1. The dispatcher must raise
  `ValueError("Unknown transcription_provider: openai_whisper — cloud mode coming in v1.1")`
  if anyone misconfigures it.
- Create `app/transcription/__init__.py`
  - `transcribe(audio_path, job_id)` dispatcher: reads config, fetches glossary prompt,
    calls correct provider
  - Raise `ValueError(f"Unknown transcription_provider: {provider}")` for unrecognised values
- Update `worker.py`:
  - Replace `from app.transcriber import transcribe` with `from app.transcription import transcribe`
  - (LLM exception handling is updated in P3 once the LLM providers are refactored)
- Update `config.py`: add `transcription_provider` and `language` to defaults
- **After all moves**: run `python -m pytest` and fix any import failures caused by relocating
  `transcriber.py`. Update test files that import `from app.transcriber import ...` to
  `from app.transcription.local import ...`. Zero test regressions before moving to P3.

### Test

```bash
# Test local path (existing behaviour)
python -m app.main
# Set transcription_provider = "whisper_local" in config.json
# Record → verify transcription still works in Czech (language = "cs")

# Test with language = "en"
# Set language = "en" in config.json
# Record English speech → verify English transcript

# Cloud transcription is v1.1 — no cloud test needed here
```

### Key constraints

- `app/transcription/local.py` must handle missing model gracefully: raise `ModelNotReadyError`
  from `app.exceptions` if the model hasn't been downloaded yet. Worker catches this and sets
  job status to `"error"` with message `"Whisper model not downloaded — go to Settings to
  download it."`
- `app/transcription/cloud.py` is v1.1 — no cloud constraints apply yet
- `ffmpeg` is never called as the bare string `"ffmpeg"` — always via `ffmpeg_exe()` from
  `app.utils`

---

## ✅ Phase P3 — Provider Abstraction: LLM — DONE

**Goal:** `notemaker.py` becomes `app/llm/anthropic_provider.py` behind a clean interface. Add OpenAI and Mistral providers. File-writing moves to `app/notes.py`.

**Completed:** 2026-05-07. `app/notes.py` created with `save_note`, `save_transcript`, `list_templates`, `load_template` (moved verbatim from `notemaker.py`). `app/llm/` package created: `anthropic_provider.py`, `openai_provider.py`, `mistral_provider.py` each implement `generate_notes(transcript, label, folder, scratch_notes, extra_context, language)` and `suggest_glossary_terms(transcript)`. Keyring services: `ObsiNote-Anthropic`, `ObsiNote-OpenAI`, `ObsiNote-Mistral`. `app/llm/__init__.py` dispatches based on `llm_provider` config. Worker updated: uses `app.llm` and `app.notes`, catches `LLMRateLimitError` for retry, writes glossary terms to `glossary_terms` column (not `error_message`). `notemaker.py` deleted. Server updated. `openai` and `mistralai` added to `requirements.txt`. Tests: 130 passed.

### Tasks

- Create `app/notes.py`
  - Move `save_note(note, label, folder, vault_path, date_str) -> str` from `notemaker.py`
    here verbatim — no logic changes
  - Move `save_transcript(transcript, label, vault_path, date_str) -> str | None` from
    `notemaker.py` here verbatim — no logic changes
  - This module has no LLM imports. It is testable without an API key.

- Create `app/llm/` package
- Move `notemaker.py` note generation logic → `app/llm/anthropic_provider.py`
  - `generate_notes(transcript, label, folder, scratch_notes, extra_context, language) -> str`
    Note: `transcript_link`, `vault_path`, `template_name`, `date_str` are NOT part of the
    provider interface — these were used in `save_note()` which now lives in `app/notes.py`.
    The provider receives only what it needs to generate text.
  - `suggest_glossary_terms(transcript) -> list[dict]`
  - Remove hardcoded `"always write in Czech"` — use `language` parameter in system prompt:
    ```python
    if language == "Auto-detect":
        lang_instruction = "Match the language of the transcript exactly."
    else:
        lang_instruction = f"Always write in {language}."
    system_prompt = f"You are a meeting notes assistant. {lang_instruction}"
    ```
  - API key from keyring: service `"ObsiNote-Anthropic"`, username `"api_key"` (unchanged)
  - Raise `LLMRateLimitError` on rate limit; `LLMAuthError` on auth failure (from `app.exceptions`)
- Keep `notemaker.py` as a thin shim that imports from `app/llm/` and `app/notes.py` for
  backwards compat during transition — delete it at end of this phase once worker is updated
- Create `app/llm/openai_provider.py`
  - `generate_notes(...)` and `suggest_glossary_terms(...)` with identical signatures
  - System prompt uses same `lang_instruction` pattern as Anthropic provider
  - Model: `gpt-4o-mini`
  - API key from keyring: service `"ObsiNote-OpenAI"`, username `"api_key"`
  - Same JSON stripping for glossary suggestions as the Anthropic provider
  - Raise `LLMRateLimitError` / `LLMAuthError` from `app.exceptions`
- Create `app/llm/mistral_provider.py`
  - Model: `mistral-small-latest`
  - API key from keyring: service `"ObsiNote-Mistral"`, username `"api_key"`
  - Use `mistralai` package (`pip install mistralai`)
  - Same interface and exception pattern
- Create `app/llm/__init__.py`
  - `generate_notes(...)` and `suggest_glossary_terms(...)` dispatchers
  - Read `llm_provider` from config, call correct provider
  - Raise `ValueError(f"Unknown llm_provider: {provider}")` for unrecognised values
- Update `worker.py`:
  - Replace `from app.notemaker import generate_notes, suggest_glossary_terms, save_note, save_transcript`
    with:
    ```python
    from app.llm import generate_notes, suggest_glossary_terms
    from app.notes import save_note, save_transcript
    ```
  - Pass `language=config.get("language_name", "Czech")` to `generate_notes`
  - The `generate_notes()` call in worker no longer receives `transcript_link`, `vault_path`,
    `template_name`, or `date_str` — these stay in `_generate()` for use with `save_note()`
  - **Fix glossary storage:** change the `suggest_glossary_terms` result from being stored in
    `error_message` (current bug) to `glossary_terms`:
    ```python
    # was: q.update_job(job_id, error_message=json.dumps(terms, ...))
    # now:
    q.update_job(job_id, glossary_terms=json.dumps(terms, ensure_ascii=False))
    ```
    The `glossary_terms` column was added in P1's `init_db()` migration. The `error_message`
    field is now reserved exclusively for actual error strings.
  - Replace the Anthropic-specific exception catch in `_generate()`:
    ```python
    # was: except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError) as exc:
    #          raise _RetryableError(str(exc)) from exc
    # now:
    except LLMRateLimitError as exc:
        raise _RetryableError(str(exc)) from exc
    ```
    Add `from app.exceptions import LLMRateLimitError, LLMAuthError` to worker imports.
    `LLMAuthError` does not need an explicit catch in `_generate()` — it propagates to the
    `except Exception` handler in `_process_next()`, which marks the job as `"error"`.
    This is correct: auth failures do not resolve themselves and must not retry.
- Update `config.py`: add `llm_provider` and `language_name` to defaults
- **After all moves**: run `python -m pytest` and fix any import failures caused by relocating
  `notemaker.py`. Update test files that import `from app.notemaker import ...` to the
  appropriate new module. Zero test regressions before moving to P4.

### Test

```bash
# Anthropic (existing behaviour)
python -m app.main
# Set llm_provider = "anthropic", language = "cs", language_name = "Czech"
# Run full pipeline — verify Czech notes generated
# Verify completed job shows NO error callout in UI (glossary terms no longer in error_message)

# Switch language
# Set language = "en", language_name = "English"
# Run pipeline on English transcript — verify English notes

# OpenAI (requires key)
# Set llm_provider = "openai"
# Run pipeline — verify notes generated

# Mistral (requires key)
# Set llm_provider = "mistral"
# Run pipeline — verify notes generated
```

### Key constraints

- All three providers must handle rate limit errors by raising `LLMRateLimitError`
  (worker catches and retries)
- All three providers must handle auth errors by raising `LLMAuthError` with message
  `"Invalid API key for {provider}. Check Settings."` — worker marks job as `error`,
  does NOT retry auth failures
- Glossary suggestion JSON parsing: strip markdown fences, catch `json.JSONDecodeError`,
  return `[]` on failure — this is non-fatal in all providers
- LLM providers never touch the filesystem — `save_note` and `save_transcript` are in
  `app/notes.py` and called by the worker
- `suggest_glossary_terms` result goes to `glossary_terms` column, never `error_message`

---

## ✅ Phase P4 — Language Selection — DONE (2026-05-07)

Changes: `SUPPORTED_LANGUAGES` in config.py · `/api/languages` route · `/settings/save` persists `llm_provider` + derives `language_name` from code · `/api-key` is now provider-aware · settings.html gains language dropdown, LLM provider dropdown, and per-provider API key fields · Tests: 143 passed.

## Phase P4 — Language Selection

**Goal:** User can select transcription and note language from a dropdown. No hardcoded Czech anywhere.

### Tasks

- Add a `SUPPORTED_LANGUAGES` list to `config.py`:
  ```python
  SUPPORTED_LANGUAGES = [
      {"code": "cs", "name": "Czech"},
      {"code": "en", "name": "English"},
      {"code": "de", "name": "German"},
      {"code": "fr", "name": "French"},
      {"code": "pl", "name": "Polish"},
      {"code": "sk", "name": "Slovak"},
      {"code": "es", "name": "Spanish"},
      {"code": "it", "name": "Italian"},
      {"code": "auto", "name": "Auto-detect"},
  ]
  ```
  `"auto"` passes `language=None` to Whisper and `"Auto-detect"` as `language_name` to the
  LLM. Providers convert `"Auto-detect"` to the prompt instruction
  `"Match the language of the transcript exactly."` (already implemented in P3).

- Add language dropdown to `settings.html`:
  - Label: "Transcription & Notes Language"
  - Options from `SUPPORTED_LANGUAGES`
  - On save: write both `language` (code) and `language_name` (name) to config

- Add `/api/languages` route to `server.py` returning `SUPPORTED_LANGUAGES`

- Expose language in the `GET /settings` template context

- Verify `app/transcription/local.py` passes `language` to Whisper correctly:
  - `language=None` for auto-detect, `language="cs"` etc for forced
  - `initial_prompt` (glossary) still works with auto-detect

- Verify all LLM providers use `language_name` correctly in their system prompts

### Test

```bash
python -m app.main
# Open Settings → verify language dropdown present with all options
# Change to English → save
# Record English meeting → verify English transcript and English notes
# Change to Auto-detect → record multilingual audio → verify reasonable result
# Change back to Czech → verify Czech output restored
```

### Key constraints

- `language_name` is what goes into the LLM prompt — it must be a natural language name or
  `"Auto-detect"`, never a code
- If `language_name` is empty or missing in config, default to `"Czech"` to avoid breaking
  existing installs
- The glossary `initial_prompt` for Whisper is language-agnostic (it's just a word list) —
  it works regardless of target language

---

## ✅ Phase P5 — Error UX — DONE (2026-05-07)

Changes: `GET /jobs` includes `audio_exists` boolean · `POST /jobs/<id>/retry` re-queues error jobs (409 if audio deleted) · error jobs show `error_message` in a red callout box · Retry button disabled when recording deleted · cloud transcribing status text mapped from `extra_context` · index page shows warning banner when `setup_complete` but no `vault_path` · 10 new tests, 137 passing.

**Goal:** Every failure mode surfaces a visible, human-readable message in the UI. No silent errors.

### Tasks

- Extend job status display in `index.html` jobs panel:
  - Status `"error"` shows the `error_message` field in a red callout, not just a red badge
  - Add a "Retry" button for jobs in error state
  - Add a "Delete" button for error jobs → `DELETE /jobs/{id}`

- Add `POST /jobs/<job_id>/retry` route to `server.py`:
  1. Fetch job from DB. Return 404 if not found.
  2. Return 400 if `status` is not `"error"`.
  3. Check that `audio_path` (or `recording_path` as fallback) exists on disk with
     `os.path.exists()`. If the file is missing, return 409:
     `{"error": "Recording file has been deleted. This job cannot be retried."}`.
  4. If file exists: `q.update_job(job_id, status="queued", error_message=None)`.
  - In the UI: the Retry button is rendered disabled (with tooltip "Recording deleted") when
    `job.audio_exists` is false. The `GET /jobs` response must include an `"audio_exists"`
    boolean field, computed server-side with `os.path.exists()` on the audio path.

- Define standard error message strings (use these exactly in all providers):
  - `"Whisper model not downloaded — go to Settings to download it."`
  - `"Transcription API error: {http_status}. Check your internet connection."`
  - `"Invalid API key for {provider}. Check Settings → API Keys."`
  - `"LLM rate limit reached. Will retry automatically."`
  - `"Output folder not set. Configure it in Settings."`
  - `"Output folder not found: {path}"`
  - `"Audio file missing — recording may have been deleted."`

- Add mode-specific status text during processing:
  - Private mode transcribing: `"Transcribing locally… {progress}% (est. {eta})"`
  - Cloud mode transcribing: `"Uploading audio…"` → `"Transcribing via API…"`
  - These cloud strings are written to the job's `extra_context` field by `cloud.py` (values:
    `"transcribing:uploading"` and `"transcribing:processing"`). The jobs panel must read
    `extra_context` for jobs in `"transcribing"` state and map them to human-readable text:
    `"transcribing:uploading"` → `"Uploading audio…"`, `"transcribing:processing"` →
    `"Transcribing via API…"`.

- Add a settings validation check: on `GET /` (main page load), if `setup_complete` is true
  but `vault_path` is empty, show a non-blocking warning banner:
  "Output folder not configured — notes cannot be saved."
  (The `/wizard` redirect for `setup_complete: false` is added in P6, where the route exists.)

### Test

```bash
python -m app.main
# Set an invalid API key → run a job → verify human-readable error appears in UI
# Click Retry → verify job re-queues and re-runs
# Delete the .mp3 for an error job → click Retry → verify 409 response and disabled button
# Remove vault_path from config → load main page → verify warning banner appears
# Set transcription_provider = "whisper_local" with no model downloaded → run job → verify correct error message
# Run a successful job → verify NO red error callout appears (glossary terms are now in glossary_terms column)
```

---

## ✅ Phase P5.5 — UI Language (Czech / English) — DONE (2026-05-15)

Changes: `app/i18n.py` created with 115-key `TRANSLATIONS` dict (`"en"`/`"cs"`) and `get_strings(lang)` · all `render_template()` calls pass `t=get_strings(config.get("ui_language", "en"))` · `window.STRINGS = {{ t | tojson }}` injected server-side before `app.js` · all hardcoded strings in `index.html`, `settings.html`, and `app.js` replaced with `t.key` / `window.STRINGS.key` · Settings page gains "Interface language" selector (English / Čeština); save triggers full page reload · `"ui_language": "en"` added to config DEFAULTS · 5 new tests in `test_i18n.py`, 2 in `test_server.py`; 225 total passing.

**Goal:** All user-facing strings in templates and JS are served in the selected UI language. English is the default for new installs. This phase must be completed before P6 so the wizard is built bilingual from day one — writing it in Czech and retrofitting translation later doubles the work.

### Tasks

- Add `ui_language` to `config.py` defaults:
  ```python
  "ui_language": "en"   # "en" or "cs"
  ```

- Create `app/i18n.py`:
  - `TRANSLATIONS: dict[str, dict[str, str]]` with keys `"en"` and `"cs"`
  - `get_strings(lang: str) -> dict[str, str]` — returns the translation dict for the given code, falls back to `"en"` for unknown codes
  - Group strings by surface area (nav, recorder, notes, jobs panel, import modals, settings, errors) so the file is easy to scan
  - ~80–100 strings covering `index.html`, `settings.html`, and the dynamic strings in `app.js`

  Key string categories:
  ```python
  TRANSLATIONS = {
      "en": {
          # Nav
          "nav_settings": "Settings",
          # Recorder
          "label_meeting_name": "Meeting name",
          "label_folder": "Folder",
          "label_template": "Template",
          "btn_start_recording": "Start Recording",
          "btn_stop_recording": "Stop Recording",
          "rec_status_label": "Recording",
          # Notes section
          "notes_label_idle": "Rough notes",
          "notes_label_active": "Quick notes",
          "btn_import_transcript": "Import transcript",
          "btn_import_audio": "Import audio",
          "scratch_placeholder": "Rough notes during the meeting...",
          # Jobs panel
          "jobs_panel_title": "Processing queue",
          "btn_clear_history": "Clear history",
          # Import transcript modal
          "modal_import_transcript_title": "Import transcript",
          # Import audio modal
          "modal_import_audio_title": "Import audio",
          # Common modal fields
          "label_meeting_date": "Meeting date",
          "label_scratch_notes": "Rough notes / context (optional)",
          "btn_cancel": "Cancel",
          "btn_import_process": "Import and process",
          # Errors (JS)
          "err_transcript_empty": "Transcript is empty.",
          "err_audio_required": "Select an audio file.",
          # ... etc.
      },
      "cs": {
          "nav_settings": "Nastavení",
          "label_meeting_name": "Název porady",
          # ... etc.
      }
  }
  ```

- Update `server.py`: every `render_template()` call receives `t=get_strings(config.get("ui_language", "en"))`

- Update `index.html` and `settings.html`:
  - Replace all hardcoded strings with `{{ t.key }}`
  - Inject `<script>window.STRINGS = {{ t | tojson }};</script>` just before `</body>` in each template so JS has the same strings at page load without a separate API call

- Update `app.js`:
  - Replace all hardcoded Czech/English strings with `window.STRINGS.key`
  - Covers: inline validation messages (`"Přepis je prázdný."`, `"Vyberte audio soubor."`), file picker hint defaults, dynamic status text

- Add UI language selector to `settings.html`:
  - Simple two-option `<select>`: English / Čeština
  - Saved via the existing `POST /settings/save`
  - Page performs a full reload after save — no AJAX needed for language switching

### Test

```bash
python -m app.main
# Verify new install defaults to English
# Open Settings → verify "UI Language" selector present with English / Čeština options
# Switch to Czech → save → verify all UI labels switch to Czech (including JS error messages)
# Switch back to English → save → verify English restored
# Run a job end-to-end → verify UI language does not affect transcription/notes language
```

### Key constraints

- Do NOT use Flask-Babel or gettext — a simple dict is sufficient and introduces zero new dependencies
- `window.STRINGS` is injected server-side, not fetched via API — avoids a flash of untranslated content
- Full page reload on language switch is intentional — keeps the implementation simple
- All future phases (P6 wizard, P7 settings extension) must add new strings to **both** `"en"` and `"cs"` dicts at the time they write the feature — never add a string to one language only
- Default is `"en"` — Czech must be explicitly selected; this matches the target audience for public distribution

---

## ✅ Phase P6 — First-Run Wizard — DONE (2026-05-15)

Changes: `templates/wizard.html` created — 5-step single-page wizard (all steps in DOM, JS shows/hides via `.active`); `GET /` redirects to `/wizard` when `setup_complete: false`; 7 new wizard routes in `server.py` (`GET /wizard`, `POST /wizard/test-llm`, `POST /wizard/test-recording`, `GET /wizard/playback/<filename>`, `POST /wizard/browse-folder`, `POST /wizard/complete`, `POST /wizard/reset`); `test_connection(key)` added to all 3 LLM providers (Anthropic, OpenAI, Mistral) — accepts raw key, does not read keyring; pywebview `FOLDER_DIALOG` for vault path with dev fallback returning `{dev_mode: true}`; model download uses polling (`/api/model-status` every 2s) instead of SSE — simpler and WebView2-reliable; Settings → "Re-run Setup Wizard" button calls `POST /wizard/reset`; all ~35 wizard strings bilingual (en + cs) in `app/i18n.py`; `conftest.py` updated to `setup_complete: True` so existing tests are unaffected; 14 new wizard tests; 239 total passing.

## Phase P6 — First-Run Wizard

**Depends on P5.5** — all wizard strings must use the `t` dict and `window.STRINGS` pattern established there. Do not write wizard UI strings in hardcoded Czech or English.

**Goal:** A new user can go from install to first successful note without reading documentation.

### Tasks

- Create `templates/wizard.html` — a 5-step single-page wizard (all steps in one HTML, JS shows/hides)

  **Step 1 — Welcome**
  - Brief description: records meetings, transcribes locally with Whisper (audio never
    leaves the machine), generates structured notes via the configured LLM API.
  - Single "Get Started" button to advance.
  - No mode selection in v1.0 — only local Whisper transcription is supported.
    Cloud transcription is planned for v1.1.

  **Step 2 — LLM API Key**
  - Heading: "Choose your AI provider for note generation"
  - Provider selector: Claude / OpenAI / Mistral (radio buttons with brief description of each)
  - API key input field (password type)
  - "Test connection" button → `POST /wizard/test-llm` which makes a minimal API call and
    returns `{ok: bool, error: str}`
  - On success: green checkmark, "Next" button activates.
  - On failure: red error message with specific text. A "Skip — I'll test later" link appears
    below the error. If skipped, step advances and a persistent orange banner appears in the
    main app: *"API connection not verified — test your key in Settings → API Keys before
    processing recordings."*
  - Never hard-block advance: a user with a valid key who is briefly offline must be able to
    complete setup.

  **Step 3 — Transcription Setup**
  - Show Whisper model selector (large-v3-turbo / large-v3) with size in MB from
    `WHISPER_MODEL_SIZES`. large-v3-turbo is pre-selected and marked "Recommended".
    Include a one-line note: "Turbo is 6× faster on CPU with near-identical quality."
    "Download now" button →
    `POST /wizard/download-model` with SSE progress stream. Cannot advance until download
    complete — the app requires a local model to function.

    **Model download resilience:** faster-whisper uses HuggingFace Hub's `hf_hub_download`
    internally, which supports HTTP Range requests and resumes partial downloads automatically.
    If the download fails mid-way (network drop, sleep), re-calling `WhisperModel()` with
    the same `download_root` resumes from where it left off — do NOT delete the partial
    download on error. The "Download now" button should become "Resume download" if a partial
    download is detected (check for incomplete files in `whisper_model_dir`). Show the
    last-known progress percentage if available.

  **Step 4 — Audio Devices**
  - Output device dropdown (for WASAPI loopback — system audio)
  - Input device dropdown (microphone)
  - "Test Recording" button — records 5 seconds, plays back via `<audio>` tag
  - "Skip" allowed — devices can be configured later in Settings

  **Step 5 — Output Folder**
  - Text input for notes output folder path
  - "Browse" button → `POST /wizard/browse-folder`
  - Note: "Your notes will be saved here as Markdown files. If you use Obsidian, point this
    to your vault."
  - "Done" button → saves all config, sets `setup_complete: true`, redirects to main UI

- Add Flask routes:
  - Update `GET /` in `server.py`: if `setup_complete` is false, redirect to `/wizard`.
    (Deferred from P5 to here — the route now exists.)
  - `GET /wizard` — serve wizard.html (only if `setup_complete: false`; otherwise redirect to `/`)
  - `POST /wizard/test-llm` — minimal API call to selected provider, return `{ok: bool, error: str}`
  - `POST /wizard/download-model` — start model download, return SSE stream with
    `{progress: int, status: str}`. Requires `threaded=True` (set in P1) — the SSE response
    is long-lived and must not block other Flask routes.
  - `POST /wizard/test-recording` — record 5s, save to temp file, return `{"filename": "<name>"}`
    (filename only — the browser cannot use a filesystem path as an `<audio>` src).
    Note: this handler blocks for the full 5-second recording duration. The UI must show a
    "Recording…" spinner and disable the button for that period. There is no cancellation
    path — if the user closes the wizard mid-recording, the recorder runs to completion
    before the response is dropped. Acceptable for a 5-second window.
  - `GET /wizard/playback/<filename>` — serve the temp recording file so the `<audio>` tag can
    play it back. Restrict to the configured temp/recordings directory to prevent path traversal.
  - `POST /wizard/browse-folder` — open native folder dialog, return selected path:
    ```python
    @app.route("/wizard/browse-folder", methods=["POST"])
    def wizard_browse_folder():
        try:
            import webview
            windows = webview.windows
            if not windows:
                raise RuntimeError("no window")
            result = windows[0].create_file_dialog(webview.FOLDER_DIALOG)
            path = result[0] if result else ""
            return jsonify({"path": path})
        except Exception:
            # Dev mode fallback — no pywebview window available
            return jsonify({
                "path": "",
                "dev_mode": True,
                "message": "Folder browser unavailable outside the packaged app — type the path manually."
            }), 200
    ```
    In the wizard JS: if `response.dev_mode` is true, show the message under the input and
    focus the text box. The wizard remains fully usable during browser-based development.
  - `POST /wizard/complete` — save all wizard config, set `setup_complete: true`

- `main.py`: after Flask starts, if `setup_complete` is false, open pywebview to `/wizard`
  instead of `/`

- Wizard must be re-accessible from Settings via "Re-run Setup Wizard" button

### Test

```bash
# Set setup_complete: false in config.json
python -m app.main
# Verify wizard opens instead of main UI
# Complete all steps — verify config.json updated correctly
# Verify main UI opens after completion
# Verify model downloaded if Private mode selected
# Re-run wizard from Settings → verify it opens again
# Test in browser (dev mode): Browse button shows helpful message instead of crashing
# Test Step 2 with bad key → click "Skip" → verify banner appears in main UI
# Test download interruption: kill network mid-download → restart → verify "Resume download" shown
```

### Key constraints

- The wizard must handle the case where the user closes it mid-way — on next launch, wizard
  opens again (`setup_complete` is still false)
- Never auto-advance steps — always require explicit user action
- LLM key test and cloud transcription key test are soft gates (skip allowed with warning
  banner) — Private mode model download is the only hard gate (model is mandatory for local)
- Do NOT delete partial model downloads on failure — HuggingFace Hub resumes automatically
- `window.create_file_dialog(webview.FOLDER_DIALOG)` returns a tuple, take `[0]`
- **Test SSE in pywebview before building the full wizard UI** — `EventSource` behavior in
  pywebview's embedded WebView2 may differ from a regular browser. Before investing in the
  download progress UI, run a minimal smoke test: one Flask route that streams five progress
  events, one wizard page that consumes them. If SSE does not work, replace the download
  progress with polling (`GET /wizard/download-status` every 2s) — simpler and equally
  functional for a one-off download.

---

## Phase P7 — Settings UI Extension

**Goal:** All new config options are accessible in Settings without using the wizard.

### Tasks

- Extend `settings.html` with new sections:

  **Provider section** (after existing API key section):
  - Transcription provider: display "Local Whisper" as read-only text with a note
    "Cloud transcription (OpenAI Whisper API) coming in v1.1". No dropdown needed in v1.0.
  - LLM provider dropdown: Claude / OpenAI / Mistral
  - API key field per provider (show only the relevant one based on dropdown selection)
  - "Test" button per API key

  **Whisper model section** (show only if transcription provider = local):
  - Current model display
  - Model selector as a table using `WHISPER_MODEL_SIZES` from `config.py` (static data —
    do not read the HuggingFace cache directory):

    | Model | Size | Quality | Notes |
    |-------|------|---------|-------|
    | large-v3-turbo | 1.5 GB | Excellent | **Recommended** — 6× faster on CPU |
    | large-v3 | 3.1 GB | Best | Maximum accuracy; slow on CPU |

  - Each row has a "Downloaded" / "Download" badge. To determine if a model is downloaded,
    check whether `<whisper_model_dir>/<model_name>/` exists and is non-empty.
  - "Download" button starts the SSE download; "Change model" replaces an existing download.
  - Read-only display of `whisper_model_dir` path (from config) so the user knows where
    models are stored.
  - Download progress bar (same SSE endpoint as wizard uses)

  **Language section**:
  - Language dropdown (from `/api/languages`)

  **Recording housekeeping section**:
  - Total size of `recordings/` folder (display in MB/GB)
  - Toggle: "Auto-delete recordings after processing" (sets `auto_delete_recordings`)
  - Number input: "Keep recordings under X GB" (sets `max_recordings_gb`) — shown only if
    auto-delete is off
  - "Delete all processed recordings now" button → `POST /recordings/cleanup` with
    confirmation dialog

  **Update section**:
  - Toggle: "Check for updates automatically"
  - "Check now" button → `POST /update-check`
  - Display: current version, last checked date

- Add Flask routes:
  - `POST /recordings/cleanup` — delete `.mp3` files (see P8 for logic)
  - `GET /recordings/size` — return total size of recordings folder
  - `POST /update-check` — check GitHub releases, return `{update_available: bool, version: str, url: str}`

### Test

```bash
python -m app.main
# Open Settings → verify all new sections present
# Switch transcription provider → verify correct API key field shown
# Switch LLM provider → verify correct API key field shown
# Change language → save → run a job → verify new language used
# Toggle auto-delete → save → run a job → verify recording deleted or kept
# Click "Delete all processed recordings" → verify only done-job recordings removed
```

---

## Phase P8 — Recordings Housekeeping (Worker Integration)

**Goal:** Worker automatically manages recording files based on config. No unbounded disk growth.

### Tasks

- Update `worker.py` after marking a job `"done"`:
  - If `auto_delete_recordings` is true **and** `job["keep_audio"] != 1`: delete the `.mp3`
    file, set `audio_path = null` in job record. The per-job `keep_audio` flag always takes
    precedence — if the user marked a recording as keep, auto-delete skips it.
  - If `auto_delete_recordings` is false and `max_recordings_gb > 0`:
    - Check total size of recordings folder
    - If over limit: delete oldest done-job recordings (by `created_at`) where
      `keep_audio != 1`, until under limit
    - Log each deletion at INFO level

- Add `GET /recordings/size` route (used by settings page to display current usage)

- Add recording size display to the jobs panel in `index.html`:
  - Show below the jobs list: "Recordings folder: X.X GB"
  - Update on page load

- Implement `cleanup_recordings(data_dir, delete_processed=False, delete_orphans=True)` utility:
  ```python
  import os
  from pathlib import Path

  def cleanup_recordings(data_dir, delete_processed=False, delete_orphans=True):
      """
      delete_processed: delete recordings for 'done' jobs where keep_audio != 1.
                        Used by POST /recordings/cleanup ("Delete all processed recordings").
      delete_orphans:   delete .mp3 files with no matching job record at all.
                        Used by both the manual button and scheduled auto-cleanup.
      """
      recordings_dir = os.path.join(data_dir, "recordings")
      all_jobs = q.list_jobs()
      known_paths = {j["audio_path"] for j in all_jobs if j.get("audio_path")}
      done_paths = {
          j["audio_path"] for j in all_jobs
          if j.get("audio_path") and j["status"] == "done" and not j.get("keep_audio")
      }
      for mp3 in Path(recordings_dir).glob("*.mp3"):
          mp3_str = str(mp3)
          if delete_processed and mp3_str in done_paths:
              logger.info("Deleting processed recording: %s", mp3)
              mp3.unlink(missing_ok=True)
          elif delete_orphans and mp3_str not in known_paths:
              logger.info("Deleting orphaned recording (no job record): %s", mp3)
              mp3.unlink(missing_ok=True)
  ```
  `POST /recordings/cleanup` (the "Delete all processed recordings now" button) calls
  `cleanup_recordings(DATA_DIR, delete_processed=True, delete_orphans=True)`.
  Worker per-job auto-delete (when `auto_delete_recordings` is true) deletes the specific
  file directly — it does not call this utility, which is intended for bulk operations.
  Each deletion is logged at INFO. `missing_ok=True` avoids a race if two runs overlap.

- Add "Keep recording" toggle per job in the jobs panel UI → writes `keep_audio = 1` to
  the job record via `PATCH /jobs/<id>` (add this route to `server.py`)

### Test

```bash
# Enable auto-delete → run a job → verify .mp3 deleted after done
# Mark a job keep_audio=1 → enable auto-delete → run → verify that recording is kept
# Disable auto-delete, set max 0.1 GB → accumulate recordings → verify oldest deleted automatically
# Create an orphaned .mp3 in recordings/ with no DB row → trigger cleanup → verify it's deleted
# Verify jobs with deleted recordings show "Recording deleted" in audio_path field
```

---

## Phase P9 — Update Notifications

**Goal:** App checks for new releases and shows a non-intrusive banner when one is available.

### Tasks

- Create `app/version.py`:
  ```python
  __version__ = "0.0.1-dev"
  ```
  Creating it here (not P11) ensures `updater.py` can import it immediately. The version string
  is finalised to `"1.0.0"` in P11.

- Create `app/updater.py`:
  ```python
  import logging
  from app.version import __version__

  logger = logging.getLogger(__name__)
  CURRENT_VERSION = __version__
  RELEASES_URL = "https://api.github.com/repos/YOUR_GITHUB_ORG/obsinote/releases/latest"

  def check_for_update() -> dict | None:
      """Returns {version, url, notes} if newer version available, else None."""
      if "YOUR_GITHUB_ORG" in RELEASES_URL:
          logger.warning("RELEASES_URL not configured — update checks disabled")
          return None
      # ... fetch and parse GitHub API response
  ```
  - Uses `urllib.request` (no extra dependency)
  - Catches all network errors silently — update check must never crash the app
  - Caches result in config: `last_update_check`, `latest_known_version`
  - Only checks if `check_updates` is true in config and >24h since last check
  - The `YOUR_GITHUB_ORG` guard prevents 404 noise in dev and makes the missing config
    obvious in logs

- Call `check_for_update()` in a daemon thread from `main.py` on startup (after Flask is up)

- Add `POST /update-check` route to `server.py` (manual trigger from settings)

- Add update banner to `index.html`:
  - Hidden by default; shown via `GET /update-status` polling on page load
  - Banner text: "ObsiNote {version} is available. [Download]"
  - [Download] opens the release URL using `webbrowser.open(url)` (stdlib) — do NOT use
    `os.startfile(url)`, which relies on the URL having a registered file handler and can
    silently do nothing if the system default for HTTP is not a browser
  - "Dismiss" button hides banner for the session (not persisted)

- Add `GET /update-status` route: returns `{available: bool, version: str, url: str}`

### Test

```bash
# version.py starts at "0.0.1-dev" — just point RELEASES_URL at a real release (no temp override needed)
python -m app.main
# Verify update banner appears
# Click Download → verify browser opens to correct URL
# Click Dismiss → verify banner gone for session
# Restart app → verify banner reappears
# Set RELEASES_URL to placeholder → verify update check disabled silently (check log)
```

---

## Phase P11 — PyInstaller Packaging

> **Note:** Phase P10 was removed (license key enforcement is not used — the app is open-source
> GPL v3 with a paid convenience installer). Phase numbering jumps P9 → P11.

**Goal:** App builds to a single `.exe` that runs without Python installed.

### Tasks

- Create `installer/build.spec` (PyInstaller spec file). The snippet below shows the key
  additions — a complete spec also requires `Analysis`, `PYZ`, `EXE`, and `COLLECT` blocks.
  Use `pyi-makespec app/main.py` to generate a skeleton, then apply these additions to it:
  ```python
  from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

  binaries = (
      collect_dynamic_libs('pyaudiowpatch') +   # PortAudio DLLs — not auto-detected
      collect_dynamic_libs('ctranslate2')        # faster-whisper wraps ctranslate2; its DLLs
  )                                              # are also not auto-detected

  datas = (
      collect_data_files('faster_whisper') +
      collect_data_files('ctranslate2') +        # ONNX runtime + model config files
      collect_data_files('webview')
  )

  # Key inclusions in the Analysis block:
  # - app/, templates/, static/, assets/ as datas
  # - ffmpeg.exe bundled in installer/ffmpeg/
  # - faster-whisper model is NOT bundled — downloaded at runtime to whisper_model_dir
  # - hiddenimports: pyaudiowpatch, faster_whisper, ctranslate2, webview,
  #                  anthropic, openai, mistralai
  ```

- Critical PyInstaller options:
  - `--onedir` (not `--onefile`) — avoids slow extraction on launch; Inno Setup will wrap it
  - `--noconsole` — no terminal window
  - `--icon assets/icon.ico`
  - Include `webview` data files: `webview` package has `.js` and `.html` assets that must
    be included explicitly
  - Include `faster_whisper` data: its ONNX runtime files must be included
  - `binaries = collect_dynamic_libs('pyaudiowpatch')` — PortAudio DLLs are not auto-detected
    by PyInstaller; without this the packaged app silently fails to record

- `ffmpeg` path: all modules already use `ffmpeg_exe()` from `app.utils` (done in P2).
  No per-module changes needed in P11. Verify `app/utils.py` is included in the spec.

- Add `installer/ffmpeg/` directory — place `ffmpeg.exe` and `ffprobe.exe` here before
  building. These are bundled by Inno Setup into the install directory.
  For local testing of the PyInstaller output (`dist/obsinote/obsinote.exe`) before running
  Inno Setup, copy `ffmpeg.exe` and `ffprobe.exe` directly into `dist/obsinote/` — the
  `sys.frozen` path detection in `ffmpeg_exe()` looks for them next to the executable.

- `autostart.py`: when packaged, the VBS launcher must point to `ObsiNote.exe`, not
  `pythonw.exe -m app.main`. Update `_pythonw()` and `_write_vbs()` to detect `sys.frozen`.

- Create `installer/setup.iss` (Inno Setup script):
  - Install to `{commonpf64}\ObsiNote` (Program Files)
  - Bundle the PyInstaller `dist/obsinote/` directory
  - Bundle `installer/ffmpeg/ffmpeg.exe` and `ffprobe.exe` → install directory
  - Create Start Menu shortcut
  - Create Desktop shortcut (optional, user can decline)
  - Add uninstaller
  - Do NOT install to `%APPDATA%` — that's for user data only
  - `AppVersion` read from `app/version.py` (`__version__ = "1.0.0"`)
  - Add a prerequisite check for WebView2 Runtime (pre-installed on Windows 11; may be
    missing on Windows 10). If absent, show a download prompt — do not hard-fail install.
  - **Autostart cleanup on uninstall:** add an `[UninstallRun]` entry (or a
    `[Registry]` delete section) that removes the autostart key written by `autostart.py`
    (`HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\ObsiNote`). Without this, users
    who enabled autostart will see a Windows error dialog on every subsequent login after
    uninstalling, because Windows tries to launch a now-missing executable.
  - Display `LICENSE` (GPL v3) during install via Inno Setup's `LicenseFile` directive.
    Plain text is acceptable; no conversion needed.

- Update `app/version.py` (created in P9 with `"0.0.1-dev"`):
  ```python
  __version__ = "1.0.0"
  ```

- **Code signing (required before public release, not blocking for personal use):**
  Windows SmartScreen blocks unsigned executables from unknown publishers. For a paid
  product this is a hard requirement before public distribution.
  - **OV certificate** (~€100–250/year from DigiCert, Sectigo, or SSL.com): removes the
    hard block; SmartScreen may still warn until the binary accumulates download reputation
    (~500–1000 installs). Acceptable for launch.
  - **EV certificate** (~€300–500/year): removes SmartScreen warning on the very first
    download. Best user experience.
  - Signing procedure (run after PyInstaller, before Inno Setup, and again on the installer):
    ```
    signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a dist\obsinote\obsinote.exe
    signtool sign /tr http://timestamp.digicert.com /td sha256 /fd sha256 /a ObsiNoteSetup.exe
    ```
  - Add code signing as a required step in P12 pre-release checklist.

### Build procedure (document this for future use):

```bash
# 1. Place ffmpeg.exe and ffprobe.exe in installer/ffmpeg/
# 2. Activate venv
# 3. pip install pyinstaller
# 4. pyinstaller installer/build.spec
# 5. Copy ffmpeg.exe and ffprobe.exe into dist/obsinote/ for local testing
# 6. Test dist/obsinote/obsinote.exe directly — verify it launches AND verify recording works
#    (audio recording is the most common DLL failure point)
# 7. Sign dist/obsinote/obsinote.exe with signtool (required before public release)
# 8. Open installer/setup.iss in Inno Setup Compiler → Build
# 9. Sign ObsiNoteSetup.exe with signtool
# 10. Test the resulting Setup.exe on a clean Windows 10 machine (no Python)
```

### Test checklist (must pass on a machine with NO Python installed)

```
[ ] Installer runs without admin prompt (or with appropriate UAC)
[ ] App launches from Start Menu
[ ] App launches from Desktop shortcut
[ ] Tray icon appears
[ ] Main window opens
[ ] Wizard appears on first launch
[ ] Recording works (system audio + mic) — verify no PortAudio/DLL errors in log
[ ] Transcription works (both providers)
[ ] Note generation works (all providers)
[ ] Auto-start toggle works
[ ] Uninstaller removes all app files (user data in %APPDATA% is preserved)
[ ] Uninstaller removes the autostart registry key if autostart was enabled
[ ] SmartScreen does not block install (requires signed binary)
```

### Key constraints

- Test on Windows 10 as well as Windows 11 — WASAPI loopback works on both
- WebView2 Runtime is pre-installed on Windows 11; for Windows 10 it may need a separate
  installer step
- `pyaudiowpatch` DLLs must be explicitly collected with `collect_dynamic_libs` — without
  this, recording silently fails in the packaged build even though it works in dev
- `ctranslate2` DLLs and data files must also be explicitly collected — faster-whisper wraps
  ctranslate2 internally, and its DLLs are not auto-detected by PyInstaller. Missing them
  causes transcription to silently fail (app launches fine, model loads, but no output)
- The Whisper model is stored at `whisper_model_dir` (from config, defaulting to
  `%LOCALAPPDATA%\ObsiNote\models`) — never bundled in the installer
- Inno Setup uninstaller must clean up the autostart registry key

---

## Phase P12 — Final Polish & Release Prep

**Goal:** Documented, tested, GPL v3-licensed, ready to list on Gumroad.

### Tasks

- Write `README.md` for end users (not developers):
  - What it does (one paragraph)
  - System requirements: Windows 10/11, internet for cloud mode or API calls
  - Two install paths: (1) download the pre-built installer from Gumroad, or (2) clone the
    repo and run from source (Python 3.11+, see requirements.txt)
  - First launch walkthrough (3 sentences — wizard handles the rest)
  - FAQ: "Where are my notes?", "Where is my data stored?", "How do I change the language?",
    "How do I switch from Private to Cloud mode?", "What data is sent to third parties?",
    "Is the source code available?" (yes — GPL v3, link to GitHub)

- Write `docs/PRIVACY_POLICY.md`:
  - What data the app collects: none directly. No telemetry, no analytics, no crash reporting.
  - What data leaves the machine:
    - In Private mode: transcript text is sent to the configured LLM API (Anthropic/OpenAI/
      Mistral) for note generation. Audio never leaves the machine.
    - In Cloud mode: audio is additionally sent to the OpenAI Whisper API for transcription.
  - Where API keys are stored: Windows Credential Manager only. Never in files, never in logs.
  - Where user data is stored: `%APPDATA%\ObsiNote\` and `%LOCALAPPDATA%\ObsiNote\models\`.
    No cloud sync. User controls deletion.
  - Contact email for privacy queries.
  - Required for GDPR compliance (developer and primary audience are EU-based). Link this
    document from the Gumroad product page and from the app's Settings → About section.

- Add a `LICENSE` file at the repo root containing the full GPL v3 license text.
  Obtain the canonical text from https://www.gnu.org/licenses/gpl-3.0.txt — do not
  paraphrase or shorten it. Inno Setup displays this during install (already wired in P11).
  Link from the GitHub repo and from the Gumroad product description.
  **This file must be committed before the repository is made public.**

- Review all UI strings — replace any remaining hardcoded Czech labels with the configured
  language where applicable (status badges in the jobs panel are UI chrome, keep them in
  English for international release)

- Set log level default to `"INFO"` in config defaults (was `"DEBUG"` during development)

- Add a "Send log to developer" section in Settings (user-initiated only):
  - **"Copy log to clipboard" button** — reads last 200 lines of `obsinote.log`, writes to
    clipboard via `subprocess.run(['clip'], input=text, encoding='utf-8', shell=True)` (Windows
    built-in `clip` command, no extra dependency). User can then paste into an email or issue.
  - **"Open log file" button** — `os.startfile(log_path)` opens the file in the default text
    editor. User can attach it manually.
  - Do NOT use a mailto: link — email client body limits (2KB–32KB depending on client) make
    it unreliable for log data. Never auto-send anything.

- Add support channel link to Settings → About section: a GitHub issues URL or support
  email address. Without this, frustrated customers dispute charges with their bank instead
  of contacting you. Also set this email on the Gumroad product page under "Support email".

- **Pre-release checklist:**
  ```
  [ ] Choose final product name — confirm no trademark conflict with "Obsidian" / Dynalist
  [ ] Replace YOUR_GITHUB_ORG in updater.py with actual GitHub repo path
  [ ] Remove the YOUR_GITHUB_ORG guard log warning from updater.py
  [ ] Verify app/version.py reads "1.0.0" (set in P11)
  [ ] Sign obsinote.exe and ObsiNoteSetup.exe with signtool
  [ ] Submit signed installer to Microsoft malware portal for whitelisting:
      https://www.microsoft.com/en-us/wdsi/filesubmission
      (free, typically resolves within days — prevents Defender false-positive flags)
  [ ] Test update banner end-to-end: temporarily set __version__ = "0.0.1" in app/version.py,
      point RELEASES_URL at a real release, verify banner appears, then restore "1.0.0"
  [ ] Set log_level default to "INFO" in config.py
  [ ] Privacy policy URL live and linked from Gumroad product page
  [ ] GPL v3 LICENSE file present at repo root and displayed during install
  [ ] Support email set on Gumroad product page
  [ ] git tag v1.0.0
  [ ] Push tag and source to GitHub — repo must be public before Gumroad listing goes live
  ```

- Gumroad setup:
  - Create product under the final product name (not "ObsiNote" — see trademark note above)
  - Price: €19 (one-time)
  - **Do not enable license key generation** — the app does no key validation
  - Upload the signed installer `.exe` as the download file
  - Link privacy policy in product description
  - Link GitHub repo in product description — "Source code available on GitHub under GPL v3"
  - Set support email
  - Write a product description emphasising: local/private, one-time payment, no subscription,
    user brings their own API keys (and therefore controls their own API costs), open source

- Tag the release on GitHub: `git tag v1.0.0`

### Final end-to-end test matrix

| Mode | LLM | Language | Expected result |
|------|-----|----------|-----------------|
| Private | Anthropic | Czech | ✓ local transcript, Czech notes |
| Private | OpenAI | English | ✓ local transcript, English notes |
| Private | Mistral | Auto-detect | ✓ local transcript, language matched to transcript |

---

## Requirements After All Phases

```
# requirements.txt
flask
faster-whisper
pyaudiowpatch
anthropic
openai
mistralai
keyring
pystray
Pillow
pywebview
```

System dependencies (bundled in installer, not in requirements.txt):
- `ffmpeg.exe` and `ffprobe.exe` — bundled by Inno Setup

---

## Key Constraints (Carry Forward from MVP)

- **Windows 10 and 11** — WASAPI loopback is Windows-specific; no macOS/Linux scope
- **`python -m app.X`** — always run as module, never `python app/X.py`
- **Read files with `errors='replace'`** — CP1250 encoding risk on terminal-redirected files
- **pystray on main thread** — Win32 requirement; pywebview also on main thread via
  `run_detached()`
- **API keys via keyring only** — never in `config.json`, never in env vars, never in logs
- **Paths via `os.path.join()`** — never hardcoded slashes
- **Claude JSON fences** — strip markdown fences before `json.loads()` in all providers
- **Stale dict bug** — always re-fetch job from SQLite after transcription step in worker
- **Port conflict** — if port 5000 is taken, try 5001–5010; pass chosen port to pywebview URL
- **Single instance** — a Windows named mutex `"Global\\ObsiNote"` is already created in
  `main.py` on startup; a second launch detects `ERROR_ALREADY_EXISTS` and exits immediately.
  Do not remove this — duplicate instances would race on the same SQLite job queue.
- **Flask `threaded=True`** — set in P1 and must never be removed. SSE model download
  responses are long-lived; without threading they block all other Flask routes.
- **`ffmpeg_exe()` from `app.utils`** — never call `"ffmpeg"` as a bare string anywhere;
  use `app.utils.ffmpeg_exe()` so packaged builds find the bundled binary automatically
- **LLM providers return strings only** — `save_note` and `save_transcript` are in
  `app/notes.py`, called by the worker, never by providers
- **Custom exceptions in `app/exceptions.py`** — never catch provider-SDK exceptions
  (`anthropic.RateLimitError` etc.) directly in worker; catch `LLMRateLimitError` etc.
- **`glossary_terms` column, not `error_message`** — `suggest_glossary_terms` result is
  stored in the `glossary_terms` DB column (added in P1). The `error_message` column is
  reserved for actual error strings. Mixing them causes successful jobs to display JSON
  blobs in the red error callout.
- **`whisper_model_dir` defaults to `%LOCALAPPDATA%`** — not `%USERPROFILE%\.cache`,
  which may be a network path on domain machines
- **`RELEASES_URL` guard** — `updater.py` logs a warning and returns None if the URL still
  contains `YOUR_GITHUB_ORG`; update checks are silently disabled in dev
- **Do not delete partial model downloads** — HuggingFace Hub resumes automatically on
  retry; deleting the partial file forces a full re-download

---

## What Is Explicitly Out of Scope for v1.0

- macOS or Linux support
- Real-time transcription (during recording)
- Speaker diarization (who said what)
- Cloud transcription via OpenAI Whisper API — planned for v1.1
- Deepgram transcription provider — planned for v1.1
- Ollama / fully-local LLM (interesting but adds significant packaging complexity — v1.1)
- Note editing within the app
- Sync or cloud backup of notes
- Mobile companion app
- Multi-user / team licensing
