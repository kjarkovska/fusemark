# ObsiNote — Planned Changes

A running list of requested changes. Each section tracks what needs to be done, which files are affected, and any known constraints. This doc will grow as new requests are added; once finalized it becomes the implementation plan.

Sections are ordered by implementation priority.

**Implemented:** items 1–10 (pywebview window, minimize to tray, logging, UI revamp, clear history, tray tooltip, glossary in vault, transcript files, templates from vault, import transcript).

---

## 11. Transcription Performance (Open Topic)

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

<!-- Add further change requests below this line -->
