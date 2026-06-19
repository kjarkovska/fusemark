"""
prompts.py — Centralized LLM prompt management for FuseMark.

Two-layer resolution per prompt (per-prompt granularity):
  1. User override: %APPDATA%\\FuseMark\\prompts\\<file> — if present and valid
  2. Bundled default: app/prompts/<file> — shipped with the app

Editing: Settings → Open prompts folder copies the bundled defaults into the
APPDATA prompts folder on first open so the user has a starting point.
"""

import logging
import os

logger = logging.getLogger(__name__)

_BUNDLED_DIR = os.path.join(os.path.dirname(__file__), "prompts")

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


def _load(name: str) -> str:
    meta = _PROMPTS[name]
    user_path = os.path.join(_user_dir(), meta["file"])
    bundled_path = os.path.join(_BUNDLED_DIR, meta["file"])

    if os.path.exists(user_path):
        try:
            with open(user_path, "r", encoding="utf-8") as f:
                text = f.read()
            _validate(text, meta["required"])
            return text
        except Exception as exc:
            logger.warning(
                "User prompt %r is invalid (%s) — using bundled default.",
                meta["file"], exc,
            )

    with open(bundled_path, "r", encoding="utf-8") as f:
        return f.read()


def build_note_template(date: str, title: str) -> str:
    return _substitute(_load("note_template"), date=date, title=title)


def build_note_system(lang_instruction: str, template: str, glossary: str) -> str:
    raw = _load("note_system")
    return _substitute(raw, lang_instruction=lang_instruction, template=template, glossary=glossary)


def build_term_suggestion(transcript: str, existing_terms: str) -> str:
    return _substitute(_load("term_suggestion"),
                       transcript=transcript,
                       existing_terms=existing_terms)


def open_prompts_folder() -> None:
    """Open the user prompts folder, pre-populating it with bundled defaults on first open."""
    user_dir = _user_dir()
    os.makedirs(user_dir, exist_ok=True)
    if not os.listdir(user_dir):
        for meta in _PROMPTS.values():
            src = os.path.join(_BUNDLED_DIR, meta["file"])
            dst = os.path.join(user_dir, meta["file"])
            if os.path.exists(src) and not os.path.exists(dst):
                with open(src, "r", encoding="utf-8") as f:
                    content = f.read()
                with open(dst, "w", encoding="utf-8") as f:
                    f.write(content)
    try:
        os.startfile(user_dir)
    except Exception as exc:
        logger.error("Could not open prompts folder: %s", exc)
