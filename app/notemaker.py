"""
notemaker.py — Claude Haiku 3.5 note generation for ObsiNote

Two Claude calls per job:
  1. Generate structured Czech meeting notes from the transcript.
  2. Suggest up to 5 new glossary terms found in the transcript.

API key is stored in Windows Credential Manager via keyring — never in files.

CLI usage (Phase 4 test):
  python -m app.notemaker --transcript path/to/transcript.txt
  python -m app.notemaker --transcript path/to/transcript.txt --label "Standup" --folder "Other"
"""

import argparse
import json
import logging
import os
from datetime import date

import anthropic
import keyring

logger = logging.getLogger(__name__)

from app.glossary import load as load_glossary

KEYRING_SERVICE = "obsinote"
KEYRING_USERNAME = "anthropic-api-key"
MODEL = "claude-haiku-4-5-20251001"

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

---
## Transcript
{transcript_link}"""

SYSTEM_PROMPT = """\
Jsi asistent pro zápisy z porad. Píšeš výhradně česky.
Dostaneš přepis porady, případně hrubé poznámky a kontext.
Vygeneruj strukturované zápisy z porady podle šablony.

Šablona výstupu:
{template}

Glosář firemních termínů (používej kanonické formy a správný pravopis):
{glossary}

Pokyny:
- Piš vždy česky, bez ohledu na jazyk přepisu.
- Používej glosář pro správný pravopis termínů.
- Úkoly formátuj jako checkboxy: - [ ] Úkol — zodpovědná osoba
- Pokud informace v přepisu chybí, nechej sekci prázdnou — nevymýšlej.
- Název porady odvoď z obsahu, pokud není zadán.
- Vyplň pouze sekce, pro které máš data z přepisu."""

TERM_SUGGESTION_PROMPT = """\
Z tohoto přepisu porady identifikuj až 5 neobvyklých termínů, zkratek nebo vlastních jmen,
které nejsou běžnou součástí českého ani anglického slovníku.

Přepis:
{transcript}

Stávající glosář (tyto termíny přeskočíš):
{existing_terms}

Vrať odpověď jako JSON pole. Každý prvek má klíče:
  "canonical" — správná forma termínu
  "aliases"   — seznam variant (může být prázdný seznam)
  "context"   — krátké vysvětlení (1 věta)
  "type"      — jedna z hodnot: product, abbreviation, person, company, other

Pokud žádné vhodné termíny nenajdeš, vrať prázdné pole [].
Vrať pouze JSON, žádný jiný text."""


# ------------------------------------------------------------------
# API key management
# ------------------------------------------------------------------

def get_api_key():
    """Retrieve the API key from Windows Credential Manager."""
    key = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    if not key:
        raise RuntimeError(
            "Anthropic API key not found in Windows Credential Manager.\n"
            "Set it with: python -m app.notemaker --set-key"
        )
    return key


def set_api_key(key):
    """Store the API key in Windows Credential Manager."""
    keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key)
    logger.info("API key saved to Windows Credential Manager.")


# ------------------------------------------------------------------
# Note generation
# ------------------------------------------------------------------

def list_templates(vault_path):
    """Return sorted list of template name stems from {vault}/ObsiNote/Templates/."""
    if not vault_path:
        return []
    tdir = os.path.join(vault_path, "ObsiNote", "Templates")
    if not os.path.isdir(tdir):
        return []
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(tdir)
        if f.endswith(".md")
    )


def load_template(vault_path, template_name):
    """Load a template file; return None if not found (caller falls back to NOTE_TEMPLATE)."""
    if not vault_path or not template_name:
        return None
    path = os.path.join(vault_path, "ObsiNote", "Templates", f"{template_name}.md")
    if not os.path.exists(path):
        logger.warning("Template '%s' not found — using built-in", template_name)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def generate_notes(transcript, label="", folder="", scratch_notes="", extra_context="", transcript_link="", vault_path="", template_name=""):
    """
    Generate a structured Czech meeting note from a transcript.
    transcript_link: Obsidian wikilink to embed (e.g. "[[ObsiNote/Transcripts/2026-04-19 Standup]]").
                     If empty, falls back to embedding the transcript in a <details> block.
    vault_path/template_name: load a custom template from vault; falls back to NOTE_TEMPLATE.
    Returns the full markdown string.
    """
    client = anthropic.Anthropic(api_key=get_api_key())
    glossary = load_glossary()
    today = date.today().isoformat()
    title = label or "Porada"

    if transcript_link:
        t_section = transcript_link
    else:
        t_section = "<details>\n<summary>Transcript</summary>\n\n[přepis bude vložen sem]\n\n</details>"

    raw_template = load_template(vault_path, template_name)
    if raw_template:
        # Custom vault template — uses {{date}}, {{title}}, {{transcript}} placeholders
        template = (
            raw_template
            .replace("{{date}}", today)
            .replace("{{title}}", title)
            .replace("{{transcript}}", t_section)
        )
    else:
        # Built-in template — uses Python .format() style
        template = NOTE_TEMPLATE.format(date=today, title=title, transcript_link=t_section)

    system = SYSTEM_PROMPT.format(
        template=template,
        glossary=json.dumps(glossary, ensure_ascii=False, indent=2),
    )

    user_parts = [f"Přepis:\n{transcript}"]
    if scratch_notes:
        user_parts.append(f"Hrubé poznámky:\n{scratch_notes}")
    if extra_context:
        user_parts.append(f"Kontext:\n{extra_context}")
    if label:
        user_parts.append(f"Název porady: {label}")
    if folder:
        user_parts.append(f"Složka v Obsidianu: {folder}")

    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": "\n\n".join(user_parts)}],
    )

    note = message.content[0].text.strip()

    # If using the built-in <details> fallback, inject the real transcript text
    if not transcript_link and not raw_template and "<details>" in note:
        note = note.replace("[přepis bude vložen sem]", transcript)

    return note


def suggest_glossary_terms(transcript):
    """
    Ask Claude to identify up to 5 new glossary terms from the transcript.
    Returns a list of term dicts, or [] if none found or on any error.
    """
    client = anthropic.Anthropic(api_key=get_api_key())
    glossary = load_glossary()
    existing = [t["canonical"] for t in glossary.get("terms", [])]

    prompt = TERM_SUGGESTION_PROMPT.format(
        transcript=transcript,
        existing_terms=", ".join(existing) if existing else "žádné",
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if Claude wrapped the JSON
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


def save_note(note_md, label, folder, vault_path):
    """
    Write the note markdown to {vault}/ObsiNote/Meetings/{folder}/.
    Returns the path of the created file.
    """
    today = date.today().isoformat()
    filename = f"{today} {label or 'Porada'}.md"
    filename = "".join(c for c in filename if c not in r'\/:*?"<>|')

    target_dir = os.path.join(vault_path, "ObsiNote", "Meetings", folder or "Other")
    os.makedirs(target_dir, exist_ok=True)

    out_path = os.path.join(target_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(note_md)

    logger.info("Note saved: %s", out_path)
    return out_path


def save_transcript(transcript_text, label, vault_path):
    """
    Save the raw transcript to {vault}/ObsiNote/Transcripts/{date} {label}.md.
    Returns the saved path, or None if vault_path is not set.
    """
    if not vault_path:
        logger.warning("vault_path not set — transcript not saved to vault")
        return None

    today = date.today().isoformat()
    label_clean = label or "Porada"
    filename = "".join(c for c in f"{today} {label_clean}.md" if c not in r'\/:*?"<>|')

    target_dir = os.path.join(vault_path, "ObsiNote", "Transcripts")
    os.makedirs(target_dir, exist_ok=True)

    out_path = os.path.join(target_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {today} {label_clean}\n\n{transcript_text}\n")

    logger.info("Transcript saved: %s", out_path)
    return out_path


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ObsiNote note generator — Phase 4 CLI test"
    )
    parser.add_argument("--transcript", metavar="PATH", help="Path to transcript text file")
    parser.add_argument("--label", default="", help="Meeting label/title")
    parser.add_argument("--folder", default="Other", help="Obsidian subfolder (default: Other)")
    parser.add_argument("--set-key", action="store_true", help="Store Anthropic API key in Windows Credential Manager")
    args = parser.parse_args()

    if args.set_key:
        import getpass
        key = getpass.getpass("Anthropic API key: ")
        set_api_key(key.strip())
        return

    if not args.transcript:
        parser.print_help()
        return

    with open(args.transcript, "r", encoding="utf-8", errors="replace") as f:
        transcript = f.read()

    print("[notemaker] Generating notes...")  # intentional stdout output for CLI use
    note = generate_notes(
        transcript=transcript,
        label=args.label,
        folder=args.folder,
    )

    print("\n--- NOTE PREVIEW ---")
    print(note)
    print("--------------------\n")

    print("[notemaker] Suggesting glossary terms...")
    terms = suggest_glossary_terms(transcript)
    if terms:
        print("Suggested terms:")
        for t in terms:
            print(f"  {t['canonical']} — {t.get('context', '')}")
    else:
        print("No new terms suggested.")


if __name__ == "__main__":
    main()
