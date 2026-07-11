import json
import logging
from datetime import date

import keyring
import openai
from openai import OpenAI

from app.exceptions import LLMAuthError, LLMRateLimitError, LLMTransientError, LLMTruncatedError
from app.glossary import load as load_glossary
from app import prompts

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"
KEYRING_SERVICE = "FuseMark-OpenAI"
KEYRING_USERNAME = "api_key"
MAX_NOTE_TOKENS = 8192


def _get_api_key():
    key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if not key:
        raise LLMAuthError("Invalid API key for OpenAI. Check Settings → API Keys.")
    return key


def set_api_key(key):
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key)
    logger.info("OpenAI API key saved to Windows Credential Manager.")


def test_connection(key: str) -> None:
    """Make a minimal API call to verify the key. Raises LLMAuthError or LLMRateLimitError."""
    try:
        client = OpenAI(api_key=key)
        client.chat.completions.create(
            model=MODEL,
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
    except openai.AuthenticationError as exc:
        raise LLMAuthError("Invalid API key for OpenAI.") from exc
    except openai.RateLimitError as exc:
        raise LLMRateLimitError("Rate limit reached.") from exc


def generate_notes(transcript, label="", folder="", scratch_notes="", extra_context="", language="Czech", date_str="", custom_template=""):
    """Generate structured meeting notes from a transcript. Returns markdown string."""
    client = OpenAI(api_key=_get_api_key())
    glossary = load_glossary()
    today = date_str or date.today().isoformat()
    title = label or "Meeting"
    template = prompts.build_note_template(date=today, title=title)

    if language == "Auto-detect":
        lang_instruction = "Match the language of the transcript exactly."
    else:
        lang_instruction = f"Always write in {language}."

    system = prompts.build_note_system(
        lang_instruction=lang_instruction,
        template=template,
        glossary=json.dumps(glossary, ensure_ascii=False, indent=2),
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
    if custom_template:
        user_parts.append(f"Use this note structure:\n{custom_template}")

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=MAX_NOTE_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
        )
    except openai.RateLimitError as exc:
        raise LLMRateLimitError(str(exc)) from exc
    except openai.AuthenticationError as exc:
        raise LLMAuthError("Invalid API key for OpenAI. Check Settings → API Keys.") from exc
    except (openai.APIConnectionError, openai.APIStatusError) as exc:
        raise LLMTransientError(str(exc)) from exc

    if response.choices[0].finish_reason == "length":
        raise LLMTruncatedError(
            "Note generation was truncated — the transcript may be too long for a single note."
        )

    return response.choices[0].message.content.strip()


def suggest_glossary_terms(transcript):
    """Identify up to 5 new glossary terms from the transcript. Returns list of dicts or []."""
    client = OpenAI(api_key=_get_api_key())
    glossary = load_glossary()
    existing = [t["canonical"] for t in glossary.get("terms", [])]

    prompt = prompts.build_term_suggestion(
        transcript=transcript,
        existing_terms=", ".join(existing) if existing else "none",
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except openai.RateLimitError as exc:
        raise LLMRateLimitError(str(exc)) from exc
    except openai.AuthenticationError as exc:
        raise LLMAuthError("Invalid API key for OpenAI. Check Settings → API Keys.") from exc

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
