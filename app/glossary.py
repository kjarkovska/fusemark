"""
glossary.py — Glossary loading and Whisper/Claude prompt helpers

Loads glossary.json from the project root.
Provides:
  - build_whisper_prompt()  — canonical terms + aliases as a hint string for Whisper
  - load()                  — full glossary dict for use in the Claude system prompt
  - add_terms()             — append approved new terms to glossary.json
  - open_in_vscode()        — open glossary.json in VSCode after edits
"""

import json
import os
import subprocess

GLOSSARY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "glossary.json"
)


def load():
    """Return the full glossary dict. Returns {'terms': []} if file is missing."""
    if not os.path.exists(GLOSSARY_PATH):
        return {"terms": []}
    with open(GLOSSARY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


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
    Append a list of new term dicts to glossary.json.
    Each term must have at least a 'canonical' key.
    Skips any term whose canonical form already exists (case-insensitive).
    """
    glossary = load()
    existing = {t["canonical"].lower() for t in glossary.get("terms", [])}

    added = []
    for term in new_terms:
        if term["canonical"].lower() not in existing:
            glossary.setdefault("terms", []).append(term)
            existing.add(term["canonical"].lower())
            added.append(term["canonical"])

    if added:
        with open(GLOSSARY_PATH, "w", encoding="utf-8") as f:
            json.dump(glossary, f, indent=2, ensure_ascii=False)
        print(f"[glossary] Added: {', '.join(added)}")
    else:
        print("[glossary] No new terms to add.")

    return added


def open_in_vscode():
    """Open glossary.json in VSCode."""
    subprocess.Popen(["code", GLOSSARY_PATH], shell=True)
