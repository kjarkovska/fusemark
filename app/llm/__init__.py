from typing import Callable, Dict, List

from app import config as cfg

# Contracts: signatures that every LLM provider module must expose.
# args: transcript, label, folder, scratch_notes, extra_context, language, date_str, custom_template
GenerateNotesCallable = Callable[[str, str, str, str, str, str, str, str], str]
# args: transcript
SuggestTermsCallable = Callable[[str], List[Dict]]


def generate_notes(transcript: str, label: str = "", folder: str = "", scratch_notes: str = "", extra_context: str = "", language: str = "Czech", date_str: str = "", custom_template: str = "") -> str:
    """Dispatch to the configured LLM provider. Returns markdown note string."""
    config = cfg.load()
    provider = config.get("llm_provider", "anthropic")
    if provider == "anthropic":
        from app.llm.anthropic_provider import generate_notes as _gen
        return _gen(transcript, label, folder, scratch_notes, extra_context, language, date_str, custom_template)
    if provider == "openai":
        from app.llm.openai_provider import generate_notes as _gen
        return _gen(transcript, label, folder, scratch_notes, extra_context, language, date_str, custom_template)
    if provider == "mistral":
        from app.llm.mistral_provider import generate_notes as _gen
        return _gen(transcript, label, folder, scratch_notes, extra_context, language, date_str, custom_template)
    raise ValueError(f"Unknown llm_provider: {provider}")


def suggest_glossary_terms(transcript: str) -> list:
    """Dispatch to the configured LLM provider. Returns list of term dicts."""
    config = cfg.load()
    provider = config.get("llm_provider", "anthropic")
    if provider == "anthropic":
        from app.llm.anthropic_provider import suggest_glossary_terms as _suggest
        return _suggest(transcript)
    if provider == "openai":
        from app.llm.openai_provider import suggest_glossary_terms as _suggest
        return _suggest(transcript)
    if provider == "mistral":
        from app.llm.mistral_provider import suggest_glossary_terms as _suggest
        return _suggest(transcript)
    raise ValueError(f"Unknown llm_provider: {provider}")
