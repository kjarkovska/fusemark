"""Shared helpers for LLM provider modules."""

from app import prompts


def build_system_prompt(lang_instruction: str, template: str, glossary_json: str,
                         template_instructions: str = "") -> str:
    """The global system prompt, plus an optional per-template addendum.

    template_instructions (from a vault template's <!-- fusemark:prompt -->
    block, see app/notes.py split_template_prompt) is concatenated AFTER
    prompts.build_note_system() returns, rather than folded into
    note_system.txt as a new placeholder. Adding a 4th required placeholder
    there would invalidate every existing user override of that prompt file
    via _PROMPTS["note_system"]["required"] — plain string concatenation
    keeps the prompt-file contract untouched, the same approach #51 used to
    thread custom_template through without touching note_system.txt.
    """
    system = prompts.build_note_system(
        lang_instruction=lang_instruction,
        template=template,
        glossary=glossary_json,
    )
    if template_instructions:
        system = f"{system}\n\n{template_instructions}"
    return system
