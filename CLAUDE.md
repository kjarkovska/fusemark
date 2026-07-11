# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Project

**FuseMark** — a local Windows 11 desktop app for recording meeting audio, transcribing it locally with faster-whisper, and generating structured Czech meeting notes into a Markdown vault (Obsidian, Logseq, or any Markdown app) via Claude Haiku 4.5 API (+ OpenAI GPT-4o mini, Mistral Small).

Audio never leaves the machine. Recording and processing are fully decoupled so back-to-back meetings work seamlessly.

## Current Status

**v1.0.2 in progress — 3/4 PRs merged (#64/#65/#66); #67 open for review. Tests: 427 passed.**

Release build fixes: `app/main.py`, `app/server.py`, `app/tray.py`, `app/prompts.py` all updated to resolve asset/template/prompt-defaults paths from `sys._MEIPASS` when frozen (PyInstaller onedir); previously `__file__`-based paths pointed back at the source tree and caused `FileNotFoundError` on first launch of the packaged exe.

Post-review hardening (merged via PR #29): bundled-defaults dir renamed `app/prompts/` → `app/prompt_defaults/` to remove the module/dir name clash with `app/prompts.py` (user-facing `%APPDATA%\FuseMark\prompts\` path unchanged); `_load()` now wraps the bundled read and raises a clear `RuntimeError` instead of leaking `FileNotFoundError` on the note-generation path; `open_prompts_folder()` seeds each missing default per-file (forward-compat for future prompts + delete-to-reset) instead of only on an empty folder; `validate_user_prompts()` + `GET /api/prompts-status` + Settings status line surface invalid user prompts (previously silent, log-only).

- `app/recorder.py` — dual-stream capture (WASAPI loopback + mic) via `pyaudiowpatch`; ffmpeg mixes to mp3
- `app/config.py` — load/save `config.json`
- `app/queue.py` — SQLite job queue, full CRUD, state machine, startup recovery; WAL mode enabled in `init_db()`; `list_jobs(has_transcript=)` filter for two-track dispatch
- `app/worker.py` — two-track parallel processing: audio track (transcribe→generate, `worker-audio` thread) + import track (generate-only, `worker-import` thread); `_loop` preserved as alias; re-fetches job after transcription (stale dict bug fix); accepts optional `config_loader` callable for testability
- `app/transcriber.py` — faster-whisper wrapper, Czech forced, glossary initial_prompt, progress reporting to SQLite
- `app/glossary.py` — load glossary.json, build Whisper prompt, add terms, open in VSCode
- `app/notemaker.py` — Claude Haiku 4.5 (+ OpenAI GPT-4o mini, Mistral Small): generates notes, suggests glossary terms; API key via keyring
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
- Release-readiness (P11/P12): **Tier-1 hardening** — `LICENSE` (GPL v3) added; `requirements.txt` pinned to installed versions; `log_level` default `INFO`; Flask `MAX_CONTENT_LENGTH`=500 MB + JSON 413 handler + `MAX_TRANSCRIPT_CHARS` cap; `load_template()` `basename()` path-traversal guard; startup `ffmpeg` probe (`utils.ffmpeg_available()` + warning in `main.py`); unlogged `except Exception` leaks in `server.py` now log + return generic text; `pyproject.toml` (ruff pyflakes-only gate + pytest config); `.github/workflows/ci.yml` (ruff+pytest on Windows). **P11 packaging scaffold** — `installer/build.spec` (PyInstaller onedir; explicit `collect_dynamic_libs` for pyaudiowpatch+ctranslate2; pre-generates & bundles state ICOs so read-only Program Files install never writes them), `installer/setup.iss` (Inno Setup: Program Files, ffmpeg bundle, WebView2 warn-not-fail, autostart Run-key `uninsdeletevalue`), `installer/README.md` (build+sign+test procedure), `.github/workflows/release.yml` (tag→unsigned build artifact). `autostart.py` now frozen-aware (`_is_frozen()` → Run key points at `FuseMark.exe`, no VBS). `app/version.py` → 1.0.0. **P12 docs** — `docs/PRIVACY_POLICY.md`, `docs/RELEASE_CHECKLIST.md`, README install/License/Privacy sections. Tests: 366 passed. **Maintainer-only remaining: final name/trademark, code-signing cert, clean-VM SmartScreen test, Gumroad listing, `<support-email>` in privacy policy.**
- Rename (v0.9.4): full clean rename **ObsiNote → FuseMark** across code, installer, docs, and tests (46 tracked files). Stored identifiers all moved to `FuseMark`: `%APPDATA%\FuseMark` (config), `%LOCALAPPDATA%\FuseMark\models` (Whisper cache), keyring services `FuseMark-{Anthropic,OpenAI,Mistral}`, autostart Run-key value `FuseMark`, mutex `Global\FuseMark`, AppUserModelID `FuseMark.App`, window title, exe/installer names, in-vault folder `{vault}/FuseMark/`. No legacy-migration code ships (pre-release); existing dev data migrated via a one-time local script. Settings/wizard vault hints genericized (no longer Obsidian-specific) to support Logseq and other Markdown tools. `LICENSE` now carries a FuseMark GPL-v3 copyright notice. `app/version.py` → 0.9.4 (→ 1.0.0 at public release). Done on branch `chore/rename-fusemark`.

- Post-release hardening (v1.0.1): technical review (2026-07-04) filed 10 issues, tackled in three branches/PRs. **Security** (#46, closes #37/#38/#39): `@app.before_request` hook in `server.py` validates `Host` (closes DNS rebinding) and `Origin` (closes CSRF) on every route; `save_note()` in `notes.py` now `os.path.basename()`s `folder` (path-traversal guard, mirrors existing `load_template()` guard). **Reliability** (#47, closes #41/#40/#36/#17): one shared `queue.py` migration adds `progress`/`eta`/`retry_count` columns — `transcription/local.py` writes progress there instead of clobbering `extra_context` (was destroying user-entered meeting context + polluting the LLM prompt on every note); `worker.py` retry logic reads/writes `retry_count` directly instead of parsing `"retry:N:"` out of `error_message` (`_parse_retry_count()` deleted); `_conn()` sets `PRAGMA busy_timeout = 5000`; `main.py` `_quit()` calls `server.stop_recording()` to flush in-progress recordings before exit, and `recover_interrupted_jobs()` now marks ghost `'recording'` jobs `'error'` instead of leaving them stuck forever. **Privacy** (#48, closes #42): self-hosted Inter (`static/fonts/InterVariable.woff2`, official `rsms/inter` v4.1 release, SIL OFL — license bundled) replaces the Google Fonts CDN `<link>`s in all three templates + the `@import` in `style.css`; `server.py` registers the `.woff2` mimetype explicitly (`mimetypes.add_type`) since it isn't in every host's registry. `app/version.py` + `installer/setup.iss` → 1.0.1; tagged and released with a locally-built installer (Inno Setup installed via winget for this session — wasn't present before).

- Review + roadmap session (2026-07-10): second full-app review → consolidated with the 2026-07-04 review into `docs/REVIEWS.md` (single rolling review log, newest first; `docs/REVIEW.md` removed, git tracks the rename). Filed issues #51–#60 + comments on #44/#35 (glossary suggestion loop confirmed dead end-to-end: suggestions computed + stored by a paid per-job LLM call but never surfaced; `add_terms()` unreachable). Headline findings: template pickers wired to nothing (#51 — `notes.load_template()` has zero callers), recorder buffers whole meeting in RAM (#52). **Milestones created**: v1.0.2 = #51/#53/#54/#55/#56/#57/#58/#59/#60 ("meetings are safe, jobs don't die for bad reasons"); v1.1 = #52+#43 (recorder pair), #44/#35 (glossary loop), #27 (gated on #51). **CI hardened** (PR #62): release workflow now asserts tag == `app/version.py` and runs pytest before building; ruff/pytest/pyinstaller pinned in `requirements-dev.txt`; new test asserts setup.iss `MyAppVersion` == `VERSION` — **bump both files together or CI fails**; read-only token, timeouts, PR-run concurrency cancellation. Dependabot alerts enabled — immediately flagged Pillow → bumped 12.1.1→12.2.0 (PR #63; 2 high + 3 moderate CVEs; exposure low, Pillow only tints the bundled icon). Tests: 394 passed.

- v1.0.2 milestone (2026-07-11): closed all 9 issues (#51, #53–#60) across 4 branches/PRs, ordered by severity (data loss first, docs last). **Data safety** (#64, merged, closes #56/#57): `notes.save_note()`/`save_transcript()` gained an `existing_path` param — a retry of the same job overwrites its own prior output, a genuine same-day/same-label collision from a different job is uniquified (` (2)`, ` (3)`, …) instead of clobbered; `config.py` `save()` now writes via temp-file + `os.replace()`, `load()` recovers from a corrupt file (backs it up, returns defaults) instead of crashing at startup, and a new `cfg.lock()` context manager protects the one real race — `updater.check_for_update()` vs `/settings/save`. **Recording lifecycle** (#65, merged, closes #54): `RecordingService.stop()`/`start()`, `Recorder.start()`, and `main._quit()` all guard their failure paths — a `save()` failure marks the job `error` instead of stranding it, a mic-open failure cleans up the already-open loopback stream instead of leaking it, and a failed flush no longer aborts app teardown. **LLM pipeline** (#66, merged, closes #51/#53/#55/#58): `worker._generate()` now loads the user's picked vault template via `notes.load_template()` (previously wired to nothing — zero callers) and threads it through `generate_notes(custom_template=...)` in all three providers as a plain "use this note structure" line, without touching the `note_system.txt` prompt-file contract; a new `LLMTransientError` (connection/5xx/overloaded) joins `LLMRateLimitError` as retryable in all three providers + `worker._generate()`; `/jobs/<id>/retry` now resets `retry_count` to 0; note-generation `max_tokens` raised 4096→8192 with a new `LLMTruncatedError` raised on `stop_reason`/`finish_reason == "length"` instead of silently saving a cut-off note. **Minor bundle** (#67, open for review, closes #59): `/jobs/<id>/audio` 404s on an unknown job and restricts audio deletion to `done`/`error` jobs (marking "keep" is unaffected); `/wizard/test-recording` guards against a concurrent real recording (409) and cleans up on failure instead of leaking a stream; the dead `extra_context === 'transcribing:uploading'/'transcribing:processing'` comparison (pre-#47 progress hack) removed from `static/app.js`; `/update-check` no longer reimplements `updater.check_for_update()`'s fetch/parse — both share a new `updater._fetch_latest_release()`, each keeping the error-handling shape its caller needs. Also fixed CLAUDE.md's D1 doc drift (#60): intro/tech-stack table now say Haiku 4.5 (+ OpenAI/Mistral), `pyaudiowpatch`, `large-v3-turbo`, any Markdown vault. Tests: 427 passed. No version bump / release cut as part of this milestone — that's a separate follow-up once #67 merges.

Update this section at the end of every session.

## Documentation

All project documentation lives in the [`docs/`](docs/) folder:

- [`docs/BRIEF.md`](docs/BRIEF.md) — Product brief: goals, architecture, user flow, UI design, data model, cost estimate, and out-of-scope items.
- [`docs/PRODUCTION_PLAN.md`](docs/PRODUCTION_PLAN.md) — Production roadmap: phased build order (P1–P12), file structure, per-phase tasks and test commands.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — As-built architecture analysis (module map, runtime diagram, state machine, hexagonal review).

**Always read both docs files at the start of a session before making any changes.**

## How to Work on This Project

The plan is phase-based. Start each session by stating which phase you are on:

> "Read docs/BRIEF.md and docs/PRODUCTION_PLAN.md. We are working on Phase X — [phase goal]."

Work phase by phase. Each phase must reach a testable state before moving to the next. **Phase 1 (audio capture) is the highest risk** — test on real hardware before continuing.

After each phase:
```bash
git add .
git commit -m "Phase X - [description] complete"
```

## Tech Stack

| Layer | Technology |
|---|---|
| Audio capture | Python + `pyaudiowpatch` (WASAPI loopback + mic, separate streams) |
| Transcription | `faster-whisper large-v3-turbo` (local, CPU; configurable) |
| Note generation | Claude Haiku 4.5 API (`anthropic`) + OpenAI GPT-4o mini + Mistral Small |
| UI | Flask + HTML (local web app) |
| System tray | `pystray` |
| Job queue | SQLite (`sqlite3`) |
| API key storage | Windows Credential Manager (`keyring`) |
| Glossary | `glossary.json` |
| Output | Markdown → Obsidian, Logseq, or any Markdown app |

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