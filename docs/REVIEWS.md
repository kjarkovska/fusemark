# FuseMark — Technical Reviews

Consolidated review log, newest first. One file for all reviews — do not create new per-review files; append here.

| Date | Version | Scope | Findings filed as |
|---|---|---|---|
| [2026-07-10](#review-2026-07-10) | v1.0.1 | Full application review | #51–#60, comments on #44/#35 |
| [2026-07-04](#review-2026-07-04) | v1.0.0 | Full codebase: security / technical / privacy / enhancements | #36–#45 |

---

# Review: 2026-07-10

**Reviewer:** Claude (Fable 5)
**Scope:** Full application review — functional correctness, reliability, security posture, docs consistency.
**Posture:** Report only. No code was changed as part of this review.

Version reviewed: v1.0.1 (`app/version.py`), branch `chore/pin-transitive-deps` (tip of main + dep pinning).

Findings filed as GitHub issues on 2026-07-10:
F1→[#51](https://github.com/kjarkovska/fusemark/issues/51), F2→comment on [#44](https://github.com/kjarkovska/fusemark/issues/44) (relabeled bug; cross-referenced [#35](https://github.com/kjarkovska/fusemark/issues/35)), R1→[#52](https://github.com/kjarkovska/fusemark/issues/52), R2→[#53](https://github.com/kjarkovska/fusemark/issues/53), R3→[#54](https://github.com/kjarkovska/fusemark/issues/54), R4→[#55](https://github.com/kjarkovska/fusemark/issues/55), R5→[#56](https://github.com/kjarkovska/fusemark/issues/56), R6→[#57](https://github.com/kjarkovska/fusemark/issues/57), M1→[#58](https://github.com/kjarkovska/fusemark/issues/58), M2–M5→[#59](https://github.com/kjarkovska/fusemark/issues/59), D1→[#60](https://github.com/kjarkovska/fusemark/issues/60).

## TL;DR

The app is in good shape: clean module boundaries, swappable providers, 393 passing tests (verified during this review; ruff clean), and the v1.0.1 hardening from the 2026-07-04 review (below) genuinely closed its findings — Host/Origin validation, keyring-only secrets, traversal guards, self-hosted fonts, dedicated progress columns, busy_timeout, quit-flush.

Two features are **wired up but completely dead**, and they should be fixed (or removed) first:

1. **F1 (bug):** The note-template picker — offered in the recorder, both import modals, and Settings — stores a choice that never reaches note generation. `notes.load_template()` has zero callers. Every note uses the bundled default template.
2. **F2 (bug + wasted spend):** Glossary term suggestions are computed by a **second paid LLM call on every job** and stored in the DB, but no UI or route ever reads them, and `glossary.add_terms()` (the approve step) is unreachable. Confirms the suspicion behind #35.

The single biggest architectural risk is **R1**: recordings are buffered entirely in RAM (~1.5–2 GB for a 2-hour meeting) and a crash loses all audio. Everything else is medium/low.

## 1. Dead features (functional bugs)

### F1 — [High] Selected note template is never used → [#51](https://github.com/kjarkovska/fusemark/issues/51)
**Where:** Template pickers (recorder, import modals, Settings `default_template`); `app/recording_service.py:64` and the import routes persist `jobs.template`; `app/worker.py` `_generate()`; `app/llm/*`; `app/notes.py:23` `load_template()`.

**Problem:** The choice is collected and stored but `worker._generate()` never passes `job["template"]` to `generate_notes()`, no provider accepts a template parameter, and `load_template()` — with its traversal guard and "caller falls back to built-in" docstring — has zero callers. Every note is generated from the bundled `note_template.md` (or the `%APPDATA%\FuseMark\prompts\` override) regardless of the pick. #27 (template-scoped prompt addendum) presumes this works.

**Fix:** Thread `job["template"]` → `generate_notes()` → providers; load via `load_template()` into `build_note_system()` with fallback. Or remove the pickers.

### F2 — [High] Glossary suggestions dead-end — every job pays for an invisible LLM call → [#44](https://github.com/kjarkovska/fusemark/issues/44) (comment), relates [#35](https://github.com/kjarkovska/fusemark/issues/35)
**Where:** `app/worker.py` `_generate()` → `suggest_glossary_terms()`; `jobs.glossary_terms`; `glossary.add_terms()`.

**Problem:** After every job the worker makes a second LLM call and stores the suggested terms, but no route, template, or line of `app.js` reads `glossary_terms`, and `add_terms()` has no callers — the approve/dismiss flow promised in the BRIEF is unreachable. Extra tokens + latency per meeting for output nobody can see. (The other half of the glossary loop — `build_whisper_prompt()` → Whisper `initial_prompt`, and the glossary embedded in note-generation system prompts — **is** wired correctly.)

**Fix:** Build the approve/dismiss UI (#44), or short-circuit the suggestion call behind a config flag until it exists.

## 2. Reliability

### R1 — [High] Whole recordings buffered in RAM → [#52](https://github.com/kjarkovska/fusemark/issues/52)
`app/recorder.py` accumulates all frames in memory: ~1.5–2 GB for a 2-hour meeting (48 kHz stereo int16 loopback + mono mic), with a further transient copy in `save()`'s `b"".join()`. Long/back-to-back meetings risk swap/OOM; crash mid-meeting loses all audio (recovery can only mark the job `error`). This is U2 from the 2026-07-04 review (below), never filed then. Fix: flush incrementally to temp WAVs during capture; ffmpeg step unchanged.

### R2 — [Medium] Only rate limits retry; transient network/5xx errors hard-fail → [#53](https://github.com/kjarkovska/fusemark/issues/53)
`worker._generate()` maps only `LLMRateLimitError` to `_RetryableError`. `APIConnectionError`, 500s, 529-overloaded fall through to the generic handler → immediate `status=error` on first attempt, despite the docstring's promise of automatic retry. Fix: providers raise a retryable `LLMTransientError` for connection/5xx/overloaded; keep auth/4xx hard.

### R3 — [Medium] Unguarded recording start/stop/quit failure paths → [#54](https://github.com/kjarkovska/fusemark/issues/54)
(1) `RecordingService.stop()`: if `r.save()` raises (ffmpeg failure, "Nothing was recorded"), the job strands in `recording` and `/stop` returns a raw 500 that `app.js` can't parse. (2) `main._quit()` calls `stop_recording()` unguarded — a failed flush aborts the whole quit (teardown + `os._exit` never run). (3) `Recorder.start()` leaks the open loopback stream + PyAudio instance if the mic open fails (realistic with BT headsets). Fix: try/except around save → mark job error; try/finally in `_quit()`; cleanup partial state in `start()`.

### R4 — [Medium] Manual retry doesn't reset `retry_count` → [#55](https://github.com/kjarkovska/fusemark/issues/55)
`route_job_retry` clears `error_message` but leaves `retry_count` at 5, so the next retryable failure sends the job straight back to `error` with no fresh budget. Fallout from the #47 migration. Fix: also set `retry_count=0`.

### R5 — [Medium] Same date + label silently overwrites notes and transcripts → [#56](https://github.com/kjarkovska/fusemark/issues/56)
`save_note()`/`save_transcript()` write `{date} {label}.md` with `"w"` — a second "Standup" the same day destroys the first one's note and transcript. Fix: uniquify new paths (` (2)`); let retries of the same job reuse their stored path.

### R6 — [Medium] `config.json` writes non-atomic; read-modify-write races → [#57](https://github.com/kjarkovska/fusemark/issues/57)
`config.save()` writes in place — a crash mid-write corrupts the file, and `load()` (called from `_setup_logging()`) then throws at startup: the app won't launch until the file is deleted manually. Separately, the background updater thread and settings routes do unsynchronized load→mutate→save and can drop each other's writes. Fix: temp file + `os.replace()`, a lock around mutations, and a defaults-with-backup fallback on `JSONDecodeError`.

## 3. Minor

### M1 — `max_tokens=4096` with no truncation check → [#58](https://github.com/kjarkovska/fusemark/issues/58)
All three providers cap note output at 4096 tokens and never check `stop_reason`/`finish_reason` — long meetings can get notes cut off mid-sentence, saved as if complete. Haiku 4.5 supports up to 64K output tokens. Fix: raise the cap and treat truncation as an error.

### M2 — `/jobs/<id>/audio` crashes on unknown job; allows deleting audio of queued jobs → [#59](https://github.com/kjarkovska/fusemark/issues/59)
`get_job()` → `None` → `AttributeError` → 500; and the API (unlike the UI) permits deleting audio for a still-queued job, breaking its transcription.

### M3 — `/wizard/test-recording` has no cleanup → [#59](https://github.com/kjarkovska/fusemark/issues/59)
No try/finally around start/sleep/stop/save (leaks streams on failure); no guard against an active real recording.

### M4 — Leftover progress magic strings in `app.js` → [#59](https://github.com/kjarkovska/fusemark/issues/59)
`renderJob` still compares `job.extra_context` to `'transcribing:uploading'`/`'transcribing:processing'` — dead remnant of the pre-#47 progress hack that now matches against user-entered context text.

### M5 — `/update-check` duplicates `updater.check_for_update()` → [#59](https://github.com/kjarkovska/fusemark/issues/59)
The route reimplements the request/parse/cache/404 logic. Delegate via a `force=True` path.

## 4. Documentation

### D1 — CLAUDE.md drift → [#60](https://github.com/kjarkovska/fusemark/issues/60)
Intro says "Claude Haiku 3.5"; tech-stack table lists `sounddevice`, `large-v3`, and Obsidian-only output. Code uses Haiku 4.5 (`claude-haiku-4-5-20251001`), `pyaudiowpatch`, `large-v3-turbo` default, any Markdown vault. BRIEF.md is current.

## 5. What's in good shape

- **Security posture** (verified against the 2026-07-04 findings): loopback-only Flask with Host/Origin validation on every route; keys only in Credential Manager with masked status endpoint; traversal guards on `folder`, `template_name`, wizard playback filename; `tojson` for template injection and consistent `esc()` in `app.js`; https-only `/open-url`; size caps + 413 handler; update check never auto-executes.
- **Queue/worker design:** WAL + busy_timeout, two-track worker (audio vs. import), startup recovery incl. ghost `recording` jobs, dedicated progress/eta/retry_count columns.
- **Packaging:** frozen-path handling (`sys._MEIPASS`) consistent across modules; pre-generated ICOs for read-only Program Files; frozen-aware autostart; WebView2 warn-not-fail.
- **Tests:** 393 passing (run during this review), ruff clean.

## Appendix — What was reviewed

- All of `app/` (server, worker, queue, recorder, recording_service, transcription/*, llm/*, notes, glossary, prompts, updater, autostart, tray, config, main, utils, i18n, exceptions).
- Frontend: `static/app.js`, `templates/*.html` (string injection, job rendering/escaping).
- Packaging: `installer/setup.iss`; docs: `BRIEF.md`, `ARCHITECTURE.md`, `CLAUDE.md`, and the 2026-07-04 review below.
- Test suite executed (`python -m pytest`): 393 passed. `ruff check`: clean.

---

# Review: 2026-07-04

**Reviewer:** Claude (Fable 5)
**Scope:** Full codebase review — security (local-first, realistic threat model), technical issues, and enhancements (technical + user).
**Posture:** Report only. No code was changed as part of this review.

Version reviewed: v1.0.0 (`app/version.py`), branch `main`.

All findings below were filed as GitHub issues [#36–#45](https://github.com/kjarkovska/fusemark/issues?q=is%3Aissue) on 2026-07-04 (T1→#36, S1→#37, S2→#38, S3→#39, T2→#40, T3→#41, P1→#42, U1→#43, U3→#44, U5/U6→#45).

> **Status as of 2026-07-10:** S1/S2/S3 fixed in PR #46 (closed #37/#38/#39); T1/T2/T3 fixed in PR #47 (closed #36/#40/#41); P1 fixed in PR #48 (closed #42). Still open: U1 (#43), U3 (#44 — expanded by the 2026-07-10 review's F2), U5/U6 (#45). U2 was never filed in this round — now tracked as [#52](https://github.com/kjarkovska/fusemark/issues/52). U4 and B1–B4 remain unfiled.

## TL;DR

The app is well-structured and unusually disciplined for a personal project: API keys live in Windows Credential Manager, Flask debug is off, path-traversal guards exist on `load_template` and `wizard_playback`, request bodies are size-capped, and the update check is HTTPS-with-cert-verification and never auto-executes anything. Tests are extensive (389 passing).

Two items stand out and deserve to be fixed first:

1. **T1 (bug, high impact):** Transcription progress is written into the `extra_context` column, which then gets fed to the LLM as meeting "Context" and destroys any context the user typed. This silently degrades every generated note — the core deliverable.
2. **S1 (security, top priority):** The localhost Flask server does no `Host`/`Origin` validation and has no CSRF/token protection, so a malicious web page (via DNS rebinding) can read `/jobs`, which returns full meeting transcripts.

Everything else is medium/low or enhancement-level.

## 1. Security / Vulnerabilities

Threat model: app stays on localhost, single user. Realistic vectors considered: malicious web pages hitting the local server (CSRF/DNS rebinding), imported/pasted files, LLM prompt injection, update spoofing, API-key handling.

### S1 — [Top priority] Local server has no Host/Origin validation → DNS rebinding can read transcripts
**Where:** `app/server.py` (`run()` binds `127.0.0.1:5000`; no `before_request` hook anywhere — confirmed zero `Host`/`Origin`/CSRF handling in `app/`). `route_jobs` returns `q.list_jobs()`, which includes the full `transcript` field.

**Problem:** Binding to `127.0.0.1` prevents LAN access but does **not** stop DNS rebinding. While the tray app is running (it autostarts and stays resident), a malicious page the user visits can rebind a hostname to `127.0.0.1` and then issue same-origin requests to the app, reading responses:
- `GET /jobs` → every meeting's full transcript, labels, context, file paths.
- `GET /api-key-status` → masked key hints (`first4••••last4`) — leaks 8 characters of each API key.
- `GET /settings`, `/recordings/size`, `/api/model-status`, device enumeration — fingerprinting.

**Fix (cheap, few lines):** Add an `@app.before_request` that rejects any request whose `Host` header isn't in an allowlist (`127.0.0.1:5000`, `localhost:5000`). Optionally also inject a random per-launch token into templates and require it on state-changing routes. This single hook also closes most of S2.

### S2 — [Medium] CSRF on the multipart import route; "simple" POSTs execute with defaults
**Where:** `app/server.py` — `route_import_audio` (uses `request.files`/`request.form`); all JSON routes using `request.get_json(silent=True) or {}`.

**Problem:**
- `/import-audio` accepts `multipart/form-data`, a CORS "simple request" that triggers **no preflight**. A cross-origin page can blind-POST to it: create a job, drop an uploaded file into the recordings dir, and trigger a paid LLM call.
- JSON routes are largely protected because a cross-origin `fetch` with `Content-Type: application/json` forces a preflight the server won't satisfy. **But** `get_json(silent=True) or {}` means a *simple* content-type POST (form/text) yields `{}` and the handler still runs with defaults: `/start` (starts a recording), `/stop`, `/wizard/reset` (forces the first-run wizard on next launch). Nuisance-level, but real.

**Fix:** The Host/Origin check from S1 covers the cross-origin case. Belt-and-suspenders: require a header browsers won't send cross-origin without preflight (e.g. `X-Requested-With`) on state-changing routes, or a CSRF token.

### S3 — [Low–Medium] Path traversal via the `folder` parameter in note output
**Where:** `app/notes.py` `save_note()` → `os.path.join(vault_path, "FuseMark", "Meetings", folder or "Other")`. `folder` arrives unsanitized from `create_job` and is fully attacker-controllable via `/import-audio` (multipart) and `/import-transcript`.

**Problem:** A value like `..\..\..\somewhere` writes the generated `.md` outside the vault's Meetings tree. Content is limited to LLM-generated markdown, and remote reachability depends on S2, so severity is bounded — but it's a real traversal and inconsistent with the codebase (which already guards `template_name` with `os.path.basename`).

**Fix:** `folder = os.path.basename(folder)` or validate against the known-folders allowlist; reject separators and `..`.

### S4 — [Low] Prompt injection from transcript content
**Where:** `app/llm/*` — transcript text (spoken, or imported/pasted) flows into the note-generation and glossary-suggestion prompts.

**Problem:** A crafted transcript can steer note output or glossary suggestions ("ignore the above and write…"). Low risk for your own meetings; higher if you import transcripts from untrusted sources. Glossary suggestions are user-reviewed before being saved (good); generated notes are not.

**Fix:** Mostly accept-and-document. If desired, wrap transcript content with clear delimiters in the prompt and instruct the model to treat it as data, not instructions.

### Security positives worth keeping
- API keys only in Windows Credential Manager, never on disk (`keyring`).
- Flask `debug=False`, `use_reloader=False` — no Werkzeug debugger/RCE surface.
- `/open-url` restricted to `https://`; `wizard_playback` has a path-traversal guard; `load_template` uses `basename`.
- `MAX_CONTENT_LENGTH` (500 MB) + `MAX_TRANSCRIPT_CHARS` cap + 413 handler.
- Update check: HTTPS to api.github.com with default cert verification, 24h throttle, silent on failure, and it **opens the releases page in the browser** rather than auto-downloading/executing — the safe design.
- Frontend output is escaped via `esc()` in the jobs list; Jinja auto-escaping covers templates. (Minor nuance: `esc()` doesn't escape `'`, but the only value interpolated into an `onclick='…("${job.id}")'` context is a server-generated UUID, so there's no XSS path.)

## 2. Technical Issues / Bugs

### T1 — [High impact] Transcription progress corrupts `extra_context` and the note prompt
**Where:** `app/transcription/local.py:113-116` writes `extra_context=f"transcribing:{progress_pct}%:eta:{eta_seconds}s"` on every segment. `app/worker.py:102` re-fetches the job after transcription, and `_generate` (`worker.py:176`) passes `job["extra_context"]` to `generate_notes`, which renders it as `Context:\n…` in the user message (`app/llm/anthropic_provider.py:68-69` and peers).

**Impact:** Two failures, both silent:
1. Any meeting context the user typed while the job was queued (saved via `/jobs/<id>/context`) is **overwritten** by the progress string.
2. The LLM receives `Context: transcribing:99%:eta:0s` as if it were meeting context — garbage in the note-generation prompt for **every** job.

This directly degrades the core output. The `extra_context` column is being used as both user data and a progress channel, and the progress write wins.

**Fix:** Give transcription progress its own storage (a dedicated `progress` column, or an in-memory map keyed by job_id that `/jobs` merges in) and stop writing progress into `extra_context`. Ensure the user's context survives through generation. Update `progressFromJob`/`etaFromJob` in `static/app.js` to read the new field.

### T2 — [Medium] SQLite has no `busy_timeout` under concurrent writers
**Where:** `app/queue.py` `_conn()` — a fresh `sqlite3.connect` per call, WAL enabled once in `init_db()`. Writers: `worker-audio` + `worker-import` threads, plus Flask request threads. Transcription writes progress per segment.

**Problem:** WAL allows concurrent readers but serializes writers; with no `busy_timeout`, a second concurrent write raises `database is locked` immediately instead of waiting. Low probability today, but per-segment progress writes plus 3s UI polling make it non-zero, and it will surface as intermittent job failures.

**Fix:** `con.execute("PRAGMA busy_timeout = 5000")` in `_conn()`. One line, removes the whole class.

### T3 — [Low] Interrupted `recording` jobs are unrecoverable ghosts
**Where:** `app/queue.py` `recover_interrupted_jobs()` only resets `transcribing`/`generating`. `app/main.py` `_quit()` calls `os._exit(0)` without stopping/saving an active recording.

**Problem:** A crash or quit mid-recording loses the in-memory audio and leaves the job stuck in `recording` forever (recovery never touches it). The BRIEF's "resumes interrupted jobs" promise doesn't hold for the recording state.

**Fix:** On quit, stop+save any active recording before exit. On startup, mark leftover `recording` jobs as `error` with a clear message so they don't linger in the panel.

### T4 — [Low] `/settings/save` casts unvalidated input
**Where:** `app/server.py:311-312` — `float(data["max_recordings_gb"])`, `int(val)` on device fields.

**Problem:** Bad input raises → unhandled 500. Local-only, low severity.

**Fix:** Guard the casts and return 400 on invalid values.

### T5 — [Low] `_enforce_size_limit` re-globs the recordings dir every iteration
**Where:** `app/worker.py:234-235` recomputes total dir size inside the per-job loop (O(n²)). n is small, so cosmetic — noted for completeness, not worth its own issue.

## 3. Privacy

### P1 — [Medium] UI loads Inter from Google Fonts CDN on every launch
**Where:** `templates/index.html:7-8`, `templates/settings.html:7-8`, `templates/wizard.html:7-8` — `<link>` to `fonts.googleapis.com` / `fonts.gstatic.com`.

**Problem:** For an app whose headline promise is "audio never leaves the machine / local-first," every window open makes a request to Google, leaking the user's IP and app-usage timing. It also means the font silently fails when offline (an app explicitly designed to work without the cloud).

**Fix:** Self-host Inter (woff2) under `static/fonts/`, reference it via `@font-face` in `static/style.css`, and drop the external `<link>`s. Offline-clean and CSP-friendly.

## 4. User-Facing Enhancements

### U1 — Honest capture verification instead of a fake level meter
`static/app.js` `startLevelMeter()` animates bars from `Math.random()` — it moves whether or not audio is actually being captured. For a recorder this is misleading: a muted mic or wrong device looks identical to success, and failure only surfaces at stop (`"Nothing was recorded"`) after the whole meeting is gone. Wire the meter to real RMS from the capture streams (e.g. a lightweight `/level` endpoint), or at minimum show a "signal detected" check a few seconds after start and warn if silent.

### U2 — Bounded, crash-resilient recording for long/back-to-back sessions
`app/recorder.py` buffers all frames (two int16 streams) in memory for the entire meeting. Multi-hour sessions use real RAM and a crash loses everything. Incrementally flushing to a temp WAV during capture bounds memory and makes long recordings crash-recoverable — directly reinforces the "back-to-back meetings" selling point.

### U3 — Actually surface glossary-term suggestions in the UI
The pipeline computes and stores `glossary_terms` per job (`worker.py:187-189`) and the BRIEF describes an approve/dismiss flow, but the jobs panel never renders them. Add the approve/dismiss UI so the feature users were promised is reachable.

### U4 — Set/adjust meeting date and create folders in the recording flow
The import modals allow a date and the recorder does not; folders are pick-from-existing only. Let users create a new folder and set/adjust the meeting date on recorded jobs.

### U5 — Click-through to the generated note
After a job is `done`, `output_note_path` is known — let the user click to open the `.md` directly (and copy its path) instead of hunting in the vault.

### U6 — Actionable error messages
Errors render raw exception text (`renderJob` → `job.error_message`). Map the common cases — no API key, model not downloaded, vault not set, ffmpeg missing — to plain-language guidance with a button to the relevant Settings section.

## 5. Bigger Bets (scope-changing — flagged separately)

- **B1 — Speaker diarization** (who said what). Already "future" in the BRIEF; high value for meeting notes, meaningful effort.
- **B2 — Optional local LLM** (Ollama / llama.cpp) for note generation → fully offline, zero-cost, zero-cloud. Aligns with the privacy positioning; large effort and a quality tradeoff to validate.
- **B3 — Code signing / SmartScreen.** Already on the maintainer checklist. Worth prioritizing because the unsigned installer directly undercuts the "easy to share with friends" goal (SmartScreen scares non-technical users off).
- **B4 — Per-job cost & latency display** with token estimation across providers, so users can see what each note costs.

## Appendix — What was reviewed
- All of `app/` (server, worker, queue, recorder, recording_service, transcription, llm/*, notes, glossary, prompts, updater, autostart, tray, config, main, utils, i18n, exceptions).
- Frontend: `static/app.js`, `templates/index.html` (+ settings/wizard for the font/CSRF surface).
- Packaging/CI: `installer/setup.iss`, `installer/build.spec`, `.github/workflows/{ci,release}.yml`, `requirements.txt`, `.gitignore`.
- Verified the pinned `mistralai==2.4.5` import path (`from mistralai.client import Mistral`) actually resolves — it does; not a bug.
