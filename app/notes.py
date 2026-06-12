import logging
import os
import re
from datetime import date

logger = logging.getLogger(__name__)


def list_templates(vault_path):
    """Return sorted list of template name stems from {vault}/FuseMark/Templates/."""
    if not vault_path:
        return []
    tdir = os.path.join(vault_path, "FuseMark", "Templates")
    if not os.path.isdir(tdir):
        return []
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(tdir)
        if f.endswith(".md")
    )


def load_template(vault_path, template_name):
    """Load a template file; return None if not found (caller falls back to built-in)."""
    if not vault_path or not template_name:
        return None
    # Guard against path traversal — only the bare file stem is allowed.
    template_name = os.path.basename(template_name)
    path = os.path.join(vault_path, "FuseMark", "Templates", f"{template_name}.md")
    if not os.path.exists(path):
        logger.warning("Template '%s' not found — using built-in", template_name)
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_note(note_md, label, folder, vault_path, date_str=""):
    """
    Write the note markdown to {vault}/FuseMark/Meetings/{folder}/.
    Returns the path of the created file.
    """
    today = date_str or date.today().isoformat()
    filename = f"{today} {label or 'Porada'}.md"
    filename = "".join(c for c in filename if c not in r'\/:*?"<>|')

    target_dir = os.path.join(vault_path, "FuseMark", "Meetings", folder or "Other")
    os.makedirs(target_dir, exist_ok=True)

    note_md = re.sub(r'(?m)^(date:)\s*.*$', f'date: {today}', note_md, count=1)

    out_path = os.path.join(target_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(note_md)

    logger.info("Note saved: %s", out_path)
    return out_path


def save_transcript(transcript_text, label, vault_path, date_str=""):
    """
    Save the raw transcript to {vault}/FuseMark/Transcripts/{date} {label}.md.
    Returns the saved path, or None if vault_path is not set.
    """
    if not vault_path:
        logger.warning("vault_path not set — transcript not saved to vault")
        return None

    today = date_str or date.today().isoformat()
    label_clean = label or "Porada"
    filename = "".join(c for c in f"{today} {label_clean}.md" if c not in r'\/:*?"<>|')

    target_dir = os.path.join(vault_path, "FuseMark", "Transcripts")
    os.makedirs(target_dir, exist_ok=True)

    out_path = os.path.join(target_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {today} {label_clean}\n\n{transcript_text}\n")

    logger.info("Transcript saved: %s", out_path)
    return out_path
