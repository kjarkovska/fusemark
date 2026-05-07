import json
import logging
from datetime import date

import keyring
from mistralai.client import Mistral

from app.exceptions import LLMAuthError, LLMRateLimitError
from app.glossary import load as load_glossary

logger = logging.getLogger(__name__)

MODEL = "mistral-small-latest"
KEYRING_SERVICE = "ObsiNote-Mistral"
KEYRING_USERNAME = "api_key"

NOTE_TEMPLATE = """\
---
date: {date}
type: meeting
tags: [meeting]
---

# {date} {title}

## Participants

## Context

## Summary

## Decisions

## Action Items
- [ ] Task — responsible person

## Notes
"""

TERM_SUGGESTION_PROMPT = """\
From this meeting transcript, identify up to 5 unusual terms, abbreviations, or proper nouns \
that are not common words in any language.

Transcript:
{transcript}

Existing glossary (skip these terms):
{existing_terms}

Return a JSON array. Each element has keys:
  "canonical" — the correct form of the term
  "aliases"   — list of spelling variants (can be empty)
  "context"   — brief explanation (1 sentence)
  "type"      — one of: product, abbreviation, person, company, other

If no suitable terms are found, return an empty array [].
Return only JSON, no other text."""


def _get_api_key():
    key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if not key:
        raise LLMAuthError("Invalid API key for Mistral. Check Settings → API Keys.")
    return key


def set_api_key(key):
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key)
    logger.info("Mistral API key saved to Windows Credential Manager.")


def _handle_mistral_error(exc):
    msg = str(exc).lower()
    code = getattr(exc, "status_code", None) or getattr(exc, "http_status_code", None)
    if code == 429 or "rate limit" in msg or "429" in str(exc):
        raise LLMRateLimitError(str(exc)) from exc
    if code == 401 or "unauthorized" in msg or "invalid api key" in msg or "401" in str(exc):
        raise LLMAuthError("Invalid API key for Mistral. Check Settings → API Keys.") from exc
    raise exc


def generate_notes(transcript, label="", folder="", scratch_notes="", extra_context="", language="Czech"):
    """Generate structured meeting notes from a transcript. Returns markdown string."""
    client = Mistral(api_key=_get_api_key())
    glossary = load_glossary()
    today = date.today().isoformat()
    title = label or "Meeting"
    template = NOTE_TEMPLATE.format(date=today, title=title)

    if language == "Auto-detect":
        lang_instruction = "Match the language of the transcript exactly."
    else:
        lang_instruction = f"Always write in {language}."

    system = (
        f"You are a meeting notes assistant. {lang_instruction}\n"
        "Generate structured meeting notes from the transcript according to the template.\n\n"
        f"Output template:\n{template}\n\n"
        "Company glossary (use canonical forms and correct spelling):\n"
        f"{json.dumps(glossary, ensure_ascii=False, indent=2)}\n\n"
        "Instructions:\n"
        "- Use the glossary for correct spelling of terms.\n"
        "- Format action items as checkboxes: - [ ] Task — responsible person\n"
        "- If information is missing from the transcript, leave the section empty.\n"
        "- Fill only sections that have data from the transcript."
    )

    user_parts = [f"Transcript:\n{transcript}"]
    if scratch_notes:
        user_parts.append(f"Rough notes:\n{scratch_notes}")
    if extra_context:
        user_parts.append(f"Context:\n{extra_context}")
    if label:
        user_parts.append(f"Meeting name: {label}")
    if folder:
        user_parts.append(f"Folder: {folder}")

    try:
        response = client.chat.complete(
            model=MODEL,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
        )
    except Exception as exc:
        _handle_mistral_error(exc)

    return response.choices[0].message.content.strip()


def suggest_glossary_terms(transcript):
    """Identify up to 5 new glossary terms from the transcript. Returns list of dicts or []."""
    client = Mistral(api_key=_get_api_key())
    glossary = load_glossary()
    existing = [t["canonical"] for t in glossary.get("terms", [])]

    prompt = TERM_SUGGESTION_PROMPT.format(
        transcript=transcript,
        existing_terms=", ".join(existing) if existing else "none",
    )

    try:
        response = client.chat.complete(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        _handle_mistral_error(exc)

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        terms = json.loads(raw)
        return terms if isinstance(terms, list) else []
    except json.JSONDecodeError:
        logger.warning("Could not parse term suggestions: %s", raw[:200])
        return []
