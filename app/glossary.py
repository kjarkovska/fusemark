"""
glossary.py — Glossary management for ObsiNote

Stores the glossary as a Markdown table at {vault}/ObsiNote/Glossary.md.
Falls back to {project_root}/Glossary.md if vault_path is not configured.

Public API (all backward-compatible):
  - glossary_path()       — resolve the current glossary file path
  - load()                — return {"terms": [...]} from the Markdown table
  - build_whisper_prompt() — canonical terms + aliases as a Whisper hint string
  - add_terms(new_terms)  — append new terms, deduplicate by canonical name
  - migrate_if_needed()   — one-time migration from legacy glossary.json
  - open_in_obsidian()    — open Glossary.md in Obsidian via URI scheme
"""

import logging
import os

logger = logging.getLogger(__name__)

from app.config import DATA_DIR
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_LEGACY_JSON_PATH = os.path.join(_PROJECT_ROOT, "glossary.json")


# ------------------------------------------------------------------
# Path resolution
# ------------------------------------------------------------------

def glossary_path(vault_path=None):
    """Return the canonical path for Glossary.md."""
    if vault_path is None:
        from app import config as cfg
        vault_path = cfg.load().get("vault_path", "")
    if vault_path:
        return os.path.join(vault_path, "ObsiNote", "Glossary.md")
    logger.warning(
        "vault_path not configured — glossary stored in data directory. "
        "Configure vault path in Settings to move it to the vault."
    )
    return os.path.join(DATA_DIR, "Glossary.md")


# ------------------------------------------------------------------
# Markdown table parsing and serialisation
# ------------------------------------------------------------------

def _parse_table(lines):
    """Parse a Markdown pipe table into a list of term dicts."""
    terms = []
    header_seen = False
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not header_seen:
            header_seen = True
            continue
        # Separator row: all non-empty cells contain only hyphens, colons, spaces
        if all(set(c).issubset(set("-: ")) for c in cells if c):
            continue
        if len(cells) < 4:
            continue
        aliases_raw = cells[1].strip()
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()] if aliases_raw else []
        terms.append({
            "canonical": cells[0],
            "aliases": aliases,
            "context": cells[2],
            "type": cells[3],
        })
    return terms


def _terms_to_table_lines(terms):
    """Serialise a list of term dicts to Markdown table lines."""
    lines = [
        "# ObsiNote Glossary",
        "",
        "| Term | Aliases | Context | Type |",
        "|------|---------|---------|------|",
    ]
    for t in terms:
        aliases_str = ", ".join(t.get("aliases", []))
        lines.append(
            f"| {t['canonical']} | {aliases_str} | {t.get('context', '')} | {t.get('type', '')} |"
        )
    return lines


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def load(vault_path=None):
    """Return the full glossary as {'terms': [...]}. Returns empty if file missing."""
    path = glossary_path(vault_path)
    if not os.path.exists(path):
        return {"terms": []}
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return {"terms": _parse_table(lines)}


def _save(terms, vault_path=None):
    path = glossary_path(vault_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = _terms_to_table_lines(terms)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def build_whisper_prompt():
    """
    Build a short initial_prompt string for Whisper containing all canonical
    terms and their aliases. Whisper uses this to bias recognition toward
    known spellings.

    Example output:
      "Jira, Yira, Džira, PR, pé er, pull request"
    """
    glossary = load()
    terms = glossary.get("terms", [])
    if not terms:
        return ""
    parts = []
    for term in terms:
        parts.append(term["canonical"])
        parts.extend(term.get("aliases", []))
    return ", ".join(parts)


def add_terms(new_terms):
    """
    Append a list of new term dicts to Glossary.md.
    Skips any term whose canonical form already exists (case-insensitive).
    """
    glossary = load()
    existing_terms = glossary.get("terms", [])
    existing_lower = {t["canonical"].lower() for t in existing_terms}

    added = []
    for term in new_terms:
        if term["canonical"].lower() not in existing_lower:
            existing_terms.append(term)
            existing_lower.add(term["canonical"].lower())
            added.append(term["canonical"])

    if added:
        _save(existing_terms)
        logger.info("Added: %s", ", ".join(added))
    else:
        logger.debug("No new terms to add.")

    return added


def migrate_if_needed():
    """
    One-time migration: convert legacy glossary.json to Glossary.md.
    Deletes the JSON file after successful migration.
    Called from main.py on startup — no-op if glossary.json does not exist.
    """
    if not os.path.exists(_LEGACY_JSON_PATH):
        return
    logger.info("Migrating glossary.json -> Glossary.md ...")
    try:
        import json
        with open(_LEGACY_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _save(data.get("terms", []))
        os.remove(_LEGACY_JSON_PATH)
        logger.info("Migration complete. glossary.json deleted.")
    except Exception as exc:
        logger.error("Glossary migration failed (glossary.json preserved): %s", exc)


def open_in_obsidian(vault_path=None):
    """Open Glossary.md in Obsidian via the obsidian:// URI scheme."""
    if vault_path is None:
        from app import config as cfg
        vault_path = cfg.load().get("vault_path", "")
    if not vault_path:
        logger.warning("vault_path not set — cannot open glossary in Obsidian")
        return
    vault_name = os.path.basename(vault_path)
    uri = f"obsidian://open?vault={vault_name}&file=ObsiNote/Glossary"
    try:
        os.startfile(uri)
    except Exception as exc:
        logger.error("Could not open Obsidian URI: %s", exc)
