"""
prompts.py — Centralized LLM prompt management for FuseMark.

Two-layer resolution per prompt (per-prompt granularity):
  1. User override: %APPDATA%\\FuseMark\\prompts\\<file> — if present and valid
  2. Bundled default: app/prompt_defaults/<file> — shipped with the app

Editing: Settings → Open prompts folder seeds any missing bundled default into
the APPDATA prompts folder, so the user always has every prompt to edit.
"""

import logging
import os
from functools import lru_cache

logger = logging.getLogger(__name__)

_BUNDLED_DIR = os.path.join(os.path.dirname(__file__), "prompt_defaults")

_PROMPTS = {
    "note_template": {
        "file": "note_template.md",
        "required": ["{date}", "{title}"],
    },
    "note_system": {
        "file": "note_system.txt",
        "required": ["{lang_instruction}", "{template}", "{glossary}"],
    },
    "term_suggestion": {
        "file": "term_suggestion.txt",
        "required": ["{transcript}", "{existing_terms}"],
    },
}


def _user_dir() -> str:
    from app.config import DATA_DIR
    return os.path.join(DATA_DIR, "prompts")


def _substitute(text: str, **kwargs) -> str:
    """Replace {key} placeholders using str.replace — safe for values containing braces."""
    result = text
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result


def _validate(text: str, required: list) -> None:
    missing = [p for p in required if p not in text]
    if missing:
        raise ValueError(f"missing required placeholders: {missing}")


@lru_cache(maxsize=None)
def _read_prompt_file(path: str, mtime: float) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load(name: str) -> str:
    meta = _PROMPTS[name]
    user_path = os.path.join(_user_dir(), meta["file"])
    bundled_path = os.path.join(_BUNDLED_DIR, meta["file"])

    if os.path.exists(user_path):
        try:
            mtime = os.path.getmtime(user_path)
            text = _read_prompt_file(user_path, mtime)
            _validate(text, meta["required"])
            return text
        except Exception as exc:
            logger.warning(
                "User prompt %r is invalid (%s) — using bundled default.",
                meta["file"], exc,
            )

    try:
        mtime = os.path.getmtime(bundled_path)
        return _read_prompt_file(bundled_path, mtime)
    except OSError as exc:
        # The bundled default is the last-resort fallback — there is nothing
        # below it. Fail loudly with context instead of leaking a bare
        # FileNotFoundError up the note-generation path.
        raise RuntimeError(
            f"Bundled prompt {meta['file']!r} is missing or unreadable at "
            f"{bundled_path!r}. This is a packaging error — reinstall FuseMark."
        ) from exc


def build_note_template(date: str, title: str) -> str:
    return _substitute(_load("note_template"), date=date, title=title)


def build_note_system(lang_instruction: str, template: str, glossary: str) -> str:
    raw = _load("note_system")
    return _substitute(raw, lang_instruction=lang_instruction, template=template, glossary=glossary)


def build_term_suggestion(transcript: str, existing_terms: str) -> str:
    return _substitute(_load("term_suggestion"),
                       transcript=transcript,
                       existing_terms=existing_terms)


def validate_user_prompts() -> list:
    """Report each prompt's status for the Settings UI.

    Status is one of:
      "default" — no user override; the bundled default is in use
      "custom"  — a valid user override is in use
      "invalid" — a user override exists but was rejected (bundled default used)
    """
    user_dir = _user_dir()
    results = []
    for name, meta in _PROMPTS.items():
        entry = {"name": name, "file": meta["file"], "status": "default", "error": ""}
        user_path = os.path.join(user_dir, meta["file"])
        if os.path.exists(user_path):
            try:
                mtime = os.path.getmtime(user_path)
                text = _read_prompt_file(user_path, mtime)
                _validate(text, meta["required"])
                entry["status"] = "custom"
            except Exception as exc:
                entry["status"] = "invalid"
                entry["error"] = str(exc)
        results.append(entry)
    return results


def open_prompts_folder() -> None:
    """Open the user prompts folder, seeding any missing bundled defaults."""
    user_dir = _user_dir()
    os.makedirs(user_dir, exist_ok=True)
    # Seed each missing default individually (not gated on an empty folder), so
    # prompts added in later versions are copied for existing users too, and
    # deleting a file then reopening restores its default.
    for meta in _PROMPTS.values():
        src = os.path.join(_BUNDLED_DIR, meta["file"])
        dst = os.path.join(user_dir, meta["file"])
        if os.path.exists(src) and not os.path.exists(dst):
            mtime = os.path.getmtime(src)
            content = _read_prompt_file(src, mtime)
            with open(dst, "w", encoding="utf-8") as f:
                f.write(content)
    try:
        os.startfile(user_dir)
    except Exception as exc:
        logger.error("Could not open prompts folder: %s", exc)
