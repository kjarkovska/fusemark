"""
glossary.py — Glossary management for FuseMark

Stores the glossary as a Markdown table at {vault}/FuseMark/Glossary.md.
Falls back to {DATA_DIR}/Glossary.md if vault_path is not configured.

Public API (all backward-compatible):
  - glossary_path()       — resolve the current glossary file path
  - load()                — return {"terms": [...]} from the Markdown table
  - build_whisper_prompt() — canonical terms + aliases as a Whisper hint string
  - add_terms(new_terms)  — append new terms, deduplicate by canonical name/alias
  - migrate_if_needed()   — one-time migration from legacy glossary.json
  - open_glossary()       — open Glossary.md in the notes app (Obsidian URI or default handler)
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

from app.config import DATA_DIR
_PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
_LEGACY_JSON_PATH = os.path.join(_PROJECT_ROOT, "glossary.json")

MAX_CANONICAL_CHARS = 100
MAX_CONTEXT_CHARS = 300


# ------------------------------------------------------------------
# Path resolution
# ------------------------------------------------------------------

def glossary_path(vault_path=None):
    """Return the canonical path for Glossary.md."""
    if vault_path is None:
        from app import config as cfg
        vault_path = cfg.load().get("vault_path", "")
    if vault_path:
        return os.path.join(vault_path, "FuseMark", "Glossary.md")
    logger.warning(
        "vault_path not configured — glossary stored in data directory. "
        "Configure vault path in Settings to move it to the vault."
    )
    return os.path.join(DATA_DIR, "Glossary.md")


# ------------------------------------------------------------------
# Markdown table parsing and serialisation
#
# Cell values (canonical/alias/context/type) can contain characters that
# would otherwise corrupt the table structure — a literal "|" would split
# into extra cells, an embedded newline would break the row onto multiple
# lines. _escape_cell()/_unescape_cell() round-trip those characters through
# backslash escapes so any term text is safe to store.
# ------------------------------------------------------------------

def _escape_cell(value) -> str:
    """Make a value safe inside one Markdown pipe-table cell."""
    text = str(value if value is not None else "")
    text = text.replace("\\", "\\\\").replace("|", "\\|")
    text = text.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    return text.strip()


def _unescape_cell(value: str) -> str:
    """Inverse of _escape_cell."""
    result = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in "\\|":
            result.append(value[i + 1])
            i += 2
        else:
            result.append(value[i])
            i += 1
    return "".join(result)


def _split_row(line: str) -> list:
    """Split one Markdown table row into unescaped cell values."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    # Split on a "|" that isn't preceded by a backslash — an escaped pipe
    # inside a value must not be treated as a column separator.
    cells = re.split(r"(?<!\\)\|", line)
    return [_unescape_cell(c.strip()) for c in cells]


def _parse_table(lines):
    """Parse a Markdown pipe table into a list of term dicts."""
    terms = []
    header_seen = False
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = _split_row(line)
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
        "# FuseMark Glossary",
        "",
        "| Term | Aliases | Context | Type |",
        "|------|---------|---------|------|",
    ]
    for t in terms:
        aliases_str = ", ".join(_escape_cell(a) for a in t.get("aliases", []))
        lines.append(
            f"| {_escape_cell(t['canonical'])} | {aliases_str} | "
            f"{_escape_cell(t.get('context', ''))} | {_escape_cell(t.get('type', ''))} |"
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


def _normalize_term(raw) -> dict | None:
    """Coerce a raw term into a safe, well-typed dict, or None if unusable.

    new_terms can come straight from LLM JSON output (app/worker.py's
    suggest_glossary_terms) or a Flask request body — neither is guaranteed
    to be a well-formed {"canonical","aliases","context","type"} dict.
    """
    if not isinstance(raw, dict):
        return None
    canonical = str(raw.get("canonical") or "").strip()
    if not canonical:
        return None
    aliases_raw = raw.get("aliases") or []
    if isinstance(aliases_raw, str):
        aliases_raw = [aliases_raw]
    aliases = [str(a).strip() for a in aliases_raw if str(a).strip()]
    return {
        "canonical": canonical[:MAX_CANONICAL_CHARS],
        "aliases": aliases,
        "context": str(raw.get("context") or "").strip()[:MAX_CONTEXT_CHARS],
        "type": str(raw.get("type") or "").strip(),
    }


def add_terms(new_terms, vault_path=None):
    """
    Append a list of new term dicts to Glossary.md.

    Skips any malformed entry (not a dict, or missing/blank canonical) and
    any term whose canonical form already exists — case-insensitively,
    checked against both existing canonicals and existing aliases, so a new
    term can't collide with a name the glossary already knows under.
    """
    glossary = load(vault_path)
    existing_terms = glossary.get("terms", [])
    existing_lower = set()
    for t in existing_terms:
        existing_lower.add(t["canonical"].lower())
        existing_lower.update(a.lower() for a in t.get("aliases", []))

    added = []
    for raw in new_terms:
        term = _normalize_term(raw)
        if term is None or term["canonical"].lower() in existing_lower:
            continue
        existing_terms.append(term)
        existing_lower.add(term["canonical"].lower())
        existing_lower.update(a.lower() for a in term["aliases"])
        added.append(term["canonical"])

    if added:
        _save(existing_terms, vault_path)
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


def open_glossary(vault_path=None):
    """Open Glossary.md in the user's notes app.

    If the vault is an Obsidian vault (has a ``.obsidian/`` folder), use the
    ``obsidian://`` URI scheme so it opens in Obsidian. Otherwise open the
    Markdown file directly in the system default handler (Logseq, editor, …).
    """
    if vault_path is None:
        from app import config as cfg
        vault_path = cfg.load().get("vault_path", "")
    if not vault_path:
        logger.warning("vault_path not set — cannot open glossary")
        return
    is_obsidian_vault = os.path.isdir(os.path.join(vault_path, ".obsidian"))
    try:
        if is_obsidian_vault:
            vault_name = os.path.basename(vault_path)
            os.startfile(f"obsidian://open?vault={vault_name}&file=FuseMark/Glossary")
        else:
            md_path = glossary_path(vault_path)
            if not os.path.exists(md_path):
                logger.warning("Glossary file not found, nothing to open: %s", md_path)
                return
            os.startfile(md_path)
    except Exception as exc:
        logger.error("Could not open glossary: %s", exc)
