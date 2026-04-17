# ObsiNote — Planned Changes

A running list of requested changes. Each section tracks what needs to be done, which files are affected, and any known constraints. This doc will grow as new requests are added; once finalized it becomes the implementation plan.

---

## 1. Standalone Window via PyWebView

**Goal:** Replace browser-based UI with a native standalone window (no address bar, no tabs, no browser chrome).

**Approach:** Use `pywebview` which wraps Microsoft Edge WebView2 — pre-installed on Windows 11. Flask stays unchanged; pywebview renders the existing HTML/CSS/JS.

### Key conflict to resolve
`pystray` currently runs on the **main thread** (Win32 requirement).
`pywebview` (`webview.start()`) also requires the **main thread**.
→ Solution: call `pystray`'s `icon.run_detached()` to move it to a background thread, freeing the main thread for pywebview.

### Changes required

| File | Change |
|---|---|
| `requirements.txt` | Add `pywebview` |
| `app/main.py` | Switch pystray to `run_detached()`; launch pywebview on main thread instead of opening browser |
| `app/tray.py` | Replace `webbrowser.open()` in the "Open" menu item with a call to show/focus the pywebview window |
| `app/server.py` | Remove `webbrowser.open()` startup call |

### Implementation notes
- `webview.create_window(title, url, width, height)` → create before `webview.start()`
- Window title: `"ObsiNote"`; reasonable default size e.g. 900×700
- The pywebview window reference should be accessible from tray callbacks so "Open" can call `window.show()` or `window.minimize()` toggle
- When the pywebview window is closed by the user, trigger a clean shutdown (stop worker + tray) — wire via `webview.start(on_top=False)` and the window's `closed` event or post-`webview.start()` cleanup
- Keep DevTools disabled in production (default); can be enabled via `webview.start(debug=True)` for development

### Resolution
- Closing the window minimizes to tray. Only tray right-click → Quit exits the app.

---

## 2. Window Close → Minimize to Tray

**Goal:** Closing the pywebview window hides it rather than quitting the app. The app continues running in the tray. Only tray → Quit performs a full shutdown.

### Changes required

| File | Change |
|---|---|
| `app/main.py` | Attach a `closing` event handler to the pywebview window; call `window.hide()` and return `False` to cancel the close |
| `app/tray.py` | Ensure the "Open" menu item calls `window.show()` to restore a hidden window |

### Implementation notes
- pywebview window `closing` event: assign a callback that calls `window.hide()` and returns `False`
- The tray "Open" item must call `window.show()` (not recreate the window)
- Quit flow (tray → Quit): stop worker, stop recorder, destroy the window, then exit

---

## 3. Clear History in UI

**Goal:** Users can remove completed and failed jobs from the jobs panel without restarting the app.

### Approach
- **Per-job delete** — small ✕ button on each `done` or `error` job card; deletes that single job from SQLite
- **Bulk clear** — "Clear completed" button at the top of the jobs panel; deletes all `done` and `error` jobs in one click
- Jobs in active states (`recording`, `transcribing`, `generating`, `queued`) cannot be deleted

### Changes required

| File | Change |
|---|---|
| `app/server.py` | `DELETE /api/jobs/<id>` — delete a single job by ID (only if status is `done` or `error`) |
| `app/server.py` | `DELETE /api/jobs` — delete all `done` and `error` jobs |
| `app/queue.py` | `delete_job(job_id)` and `clear_completed()` methods |
| `templates/index.html` | ✕ button on each completed/error job card; "Clear completed" button in panel header |
| `static/` | JS handlers for both delete actions; remove card from DOM on success |

---

## 4. Tray Icon Hover — Status Tooltip

**Goal:** Hovering over the tray icon shows a tooltip with the current app status, including transcription progress.

### Approach
`pystray` supports `icon.title` — a plain string shown as the Windows tooltip on hover. Update it dynamically from worker and recorder threads.

### Example strings
- `"ObsiNote — Idle"`
- `"ObsiNote — Recording 00:23:15"`
- `"ObsiNote — Transcribing: Standup (62%)"`
- `"ObsiNote — Generating notes: Standup"`
- `"ObsiNote — 2 jobs queued"`

### Changes required

| File | Change |
|---|---|
| `app/tray.py` | Expose `set_tooltip(text)` helper that sets `icon.title`; keep within 127-char Win32 limit |
| `app/worker.py` | Call `set_tooltip()` at each state transition and on transcription progress updates |
| `app/recorder.py` | Call `set_tooltip()` with elapsed time on each timer tick (or every ~5 s) |
| `app/server.py` | Reset tooltip to "Idle" when no jobs are active |

### Implementation notes
- Progress % is already written to SQLite by the worker — read it for the tooltip string
- Timer ticks in recorder already run on a background thread; update tooltip there

---

## 5. Transcription Performance (Open Topic)

**Problem:** CPU transcription of a 1-hour meeting takes too long on a laptop CPU, even with the `small` model. This blocks the pipeline and degrades usability for long meetings.

### Options to evaluate

| Option | Speed | Privacy | Effort |
|---|---|---|---|
| GPU / CUDA (local) | Fast | Full — audio stays local | Medium — needs NVIDIA GPU + CUDA |
| `whisper.cpp` (quantized, CPU) | 3–5× faster than faster-whisper on CPU | Full | Medium |
| Mistral / Voxtral API | Very fast | Partial — audio sent to Mistral (EU-based, GDPR) | Medium |
| OpenAI / Groq Whisper API | Very fast | Low — audio leaves machine to US cloud | Low |

### Notes
- Any cloud-based transcription breaks the "audio never leaves the machine" guarantee — decision must be explicit
- Voxtral combines transcription + note generation in one call, potentially replacing both faster-whisper and Claude; see BRIEF.md Future Considerations
- `whisper.cpp` with a quantized `large-v3` model is the best-effort local path if GPU is unavailable
- **Decision needed:** acceptable privacy tradeoff for speed? GPU available?

---

## 6. Templates from Vault

**Goal:** Note output structure is driven by Markdown templates stored in the Obsidian vault under a `Templates/` folder, editable directly in Obsidian. Replaces the hardcoded template in `notemaker.py`.

### Approach
- Templates are `.md` files in `{vault}/Templates/` (e.g. `Templates/Meeting.md`, `Templates/1on1.md`)
- Placeholder syntax: `{{date}}`, `{{title}}`, `{{participants}}`, `{{summary}}`, `{{decisions}}`, `{{action_items}}`, `{{notes}}`, `{{transcript}}`
- Claude fills in each placeholder section; the template provides the structure and any static text/headings
- Fallback: if the Templates folder doesn't exist or is empty, use the built-in template (current behaviour)

### Changes required

| File | Change |
|---|---|
| `app/notemaker.py` | Load template file at generation time; pass template structure to Claude prompt |
| `app/server.py` | `GET /api/templates` — return list of template names from `{vault}/Templates/` |
| `app/config.py` | Add `default_template` field (template filename) |
| `templates/index.html` | Template selector in recorder (per-meeting) and default template in Settings |

### Open questions
- **Per-meeting selection or Settings default only?** Per-meeting adds a dropdown to every recording; Settings default is simpler. Likely: both — default in Settings, override per meeting.
- Placeholder syntax: use `{{field}}` (Obsidian-style) or something else?

---

## 7. Import Transcript from Teams / Other Tools

**Goal:** Accept a plain-text or `.vtt` transcript from Teams (or any other tool) and generate notes directly — skipping recording and transcription entirely.

### Approach
- New "Import transcript" button in the UI
- User pastes text or uploads a `.txt` / `.vtt` file
- A job is created directly in `generating` state (no `recording_path`, no `audio_path`)
- Same metadata applies: label, folder, scratch notes, extra context, template selection
- `.vtt` input: strip WebVTT timing lines and merge speaker blocks into plain text before passing to Claude

### Changes required

| File | Change |
|---|---|
| `app/server.py` | `POST /api/jobs/import` — accepts `{label, folder, transcript_text, scratch_notes, extra_context}`; creates job at `generating` state |
| `app/queue.py` | `create_from_transcript(...)` — insert job with status `generating`, transcript pre-populated |
| `app/worker.py` | Worker already handles `generating` state; no change needed if transcript is pre-filled in the job row |
| `templates/index.html` | "Import transcript" button/modal with text area + file upload + metadata fields |
| `static/` | JS for file upload (`.vtt` / `.txt`), VTT stripping, and form submission |

### Implementation notes
- `.vtt` stripping: remove lines matching `^\d{2}:\d{2}` (timestamps) and `^WEBVTT`, collapse blank lines, strip `<v SpeakerName>` tags
- Teams also exports `.docx` — out of scope for now; plain text paste covers the common case
- The import flow creates a job that appears in the jobs panel immediately in `generating` state

---

## 8. Glossary in Obsidian Vault (Markdown format)

**Goal:** Move the glossary into the Obsidian vault as a Markdown file so it renders natively in Obsidian and can be edited there directly — no VSCode needed.

### File location and format
- Path: `{vault}/ObsiNote/glossary.md`
- Format: Markdown table (renders with Obsidian's built-in table editor)

```markdown
# ObsiNote Glossary

| Term | Aliases | Context | Type |
|------|---------|---------|------|
| Jira | Yira, Džira, jira | project management tool | product |
| PR | pé er, pull request | git pull request | abbreviation |
```

- Aliases are comma-separated within the cell
- If `vault_path` is not configured, fall back to `glossary.md` in the project root with a console warning
- On first launch after the change, auto-migrate from `glossary.json` if it exists: convert to Markdown table, write to new path, delete old file

### Python parsing
No extra library needed — parse the table with stdlib `str.split('|')`, skip header and separator rows, strip whitespace from each cell. Aliases split on `','`.

### Changes required

| File | Change |
|---|---|
| `app/glossary.py` | Rewrite `load()` and `save()` to read/write Markdown table; add `glossary_path()` helper (`{vault}/ObsiNote/glossary.md`); add `migrate_if_needed()` to convert old JSON on startup |
| `app/main.py` | Call `glossary.migrate_if_needed()` after `q.init_db()` |
| `app/server.py` | `POST /open-glossary` — open in Obsidian via `obsidian://open?vault=...&file=ObsiNote/glossary` URI instead of VSCode |
| `templates/settings.html` | Rename button to "Open glossary in Obsidian" |
| `CLAUDE.md` | Update glossary references (format, location) |

### Notes
- The `ObsiNote/` subfolder in the vault groups app-managed files (glossary, and future files like config snapshots) without cluttering the vault root
- "Open in VSCode" button replaced by "Open in Obsidian" — the Markdown table is editable directly in Obsidian's table editor, making VSCode unnecessary for glossary management
- The `obsidian://` URI scheme is available on all platforms where Obsidian is installed; on Windows it opens the correct vault automatically

## 9. Logging

**Goal:** Replace all `print()` calls (53 across 7 files) with Python's `logging` module. Persistent log file for post-mortem debugging; clean console output in normal use.

### Standard

| Concern | Decision |
|---|---|
| Module | `logging` stdlib — no new dependency |
| Setup | Central config in `app/main.py`; each module gets `logger = logging.getLogger(__name__)` |
| File | `logs/obsinote.log` in the project root; `RotatingFileHandler` — 5 MB max, 3 backups |
| Console | `StreamHandler` at `WARNING` level (quiet in normal use); file handler at `DEBUG` |
| Format | `%(asctime)s [%(levelname)-8s] %(name)s: %(message)s` |
| Flask | Keep Flask's own request log on console suppressed (`log.setLevel(WARNING)` on Werkzeug logger) |

### Log level guidelines

| Level | When to use |
|---|---|
| `DEBUG` | Transcription progress %, timer ticks, per-segment detail |
| `INFO` | Job state transitions, startup/shutdown, recording start/stop |
| `WARNING` | Recoverable issues: vault not set, glossary missing, API key not found |
| `ERROR` | Job failures, unhandled exceptions, API errors |

### Changes required

| File | Change |
|---|---|
| `app/main.py` | Add `_setup_logging()` called before anything else; creates `logs/` dir, wires file + console handlers |
| `app/worker.py` | Replace 10 `print()` calls with `logger = logging.getLogger(__name__)` |
| `app/transcriber.py` | Replace 7 `print()` calls; progress updates → `DEBUG` |
| `app/queue.py` | Replace 13 `print()` calls |
| `app/notemaker.py` | Replace 11 `print()` calls; API errors → `ERROR` |
| `app/recorder.py` | Replace 8 `print()` calls |
| `app/autostart.py` | Replace 2 `print()` calls |
| `app/glossary.py` | Replace 2 `print()` calls |
| `.gitignore` | Add `logs/` |

## 10. Transcript Files in Vault

**Goal:** Save each transcript as a Markdown file in the vault under a dedicated `Transcripts/` folder, so they are searchable and readable in Obsidian independently of the meeting notes.

### File location and naming
- Path: `{vault}/Transcripts/{date} {label}.md` — flat folder, no subfolders
- Filename mirrors the meeting note (e.g. `2026-04-17 Standup.md`) for easy correlation
- Written immediately after transcription completes, before note generation — transcript is preserved even if Claude API fails

### Note template change
Currently the note embeds the full transcript in a `<details>` block. With transcript files, replace that block with an Obsidian wikilink:

```markdown
## Transcript
[[Transcripts/2026-04-17 Standup]]
```

This keeps notes clean while making the transcript one click away in Obsidian.

### Changes required

| File | Change |
|---|---|
| `app/worker.py` | After `_transcribe()`, call `save_transcript()` before `_generate()` |
| `app/notemaker.py` | Add `save_transcript(text, label, date, vault_path)` — writes `{vault}/Transcripts/{date} {label}.md`; update note template to emit wikilink instead of embedded `<details>` block |
| `app/queue.py` | Add `transcript_path` column to store the saved path (for reference/display in UI) |

### Notes
- `Transcripts/` sits at the vault root alongside `Meetings/` — keeps raw transcripts separate from structured notes
- Transcript file is plain text wrapped in minimal Markdown (just a heading); no frontmatter needed
- If `vault_path` is not set when transcription finishes, skip saving the file and keep the transcript in SQLite only (current behaviour as fallback)

<!-- Add further change requests below this line -->
