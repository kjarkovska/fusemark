import os
import pytest
from app.notes import (
    list_templates,
    load_template,
    save_note,
    save_transcript,
)


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "FuseMark" / "Templates").mkdir(parents=True)
    (tmp_path / "FuseMark" / "Meetings" / "Other").mkdir(parents=True)
    (tmp_path / "FuseMark" / "Transcripts").mkdir(parents=True)
    return str(tmp_path)


# ------------------------------------------------------------------
# list_templates()
# ------------------------------------------------------------------

def test_list_templates_missing_dir(tmp_path):
    result = list_templates(str(tmp_path))
    assert result == []


def test_list_templates_empty_vault_path():
    assert list_templates("") == []


def test_list_templates_returns_sorted_stems(vault, tmp_path):
    tdir = tmp_path / "FuseMark" / "Templates"
    (tdir / "Standup.md").write_text("template", encoding="utf-8")
    (tdir / "Planning.md").write_text("template", encoding="utf-8")
    (tdir / "Review.md").write_text("template", encoding="utf-8")
    (tdir / "notes.txt").write_text("ignored", encoding="utf-8")  # non-.md ignored
    result = list_templates(vault)
    assert result == ["Planning", "Review", "Standup"]


def test_list_templates_ignores_non_md(vault, tmp_path):
    tdir = tmp_path / "FuseMark" / "Templates"
    (tdir / "only.txt").write_text("x", encoding="utf-8")
    assert list_templates(vault) == []


# ------------------------------------------------------------------
# load_template()
# ------------------------------------------------------------------

def test_load_template_missing(vault):
    result = load_template(vault, "NonExistent")
    assert result is None


def test_load_template_empty_args():
    assert load_template("", "Something") is None
    assert load_template("/vault", "") is None


def test_load_template_reads_content(vault, tmp_path):
    content = "# {{title}}\n\nDatum: {{date}}\n\n{{transcript}}"
    (tmp_path / "FuseMark" / "Templates" / "Meeting.md").write_text(content, encoding="utf-8")
    result = load_template(vault, "Meeting")
    assert result == content


def test_load_template_reads_utf8(vault, tmp_path):
    content = "# Šablona porady\n\nÚčastníci: {{title}}"
    (tmp_path / "FuseMark" / "Templates" / "Czech.md").write_text(content, encoding="utf-8")
    result = load_template(vault, "Czech")
    assert "Šablona" in result
    assert "Účastníci" in result


# ------------------------------------------------------------------
# save_note()
# ------------------------------------------------------------------

def test_save_note_creates_file(vault):
    path = save_note("# Note content", "Standup", "Other", vault, date_str="2026-01-15")
    assert os.path.exists(path)
    assert open(path, encoding="utf-8").read() == "# Note content"


def test_save_note_uses_date_str(vault):
    path = save_note("content", "Meeting", "Other", vault, date_str="2025-03-10")
    assert "2025-03-10" in os.path.basename(path)


def test_save_note_fallback_label(vault):
    path = save_note("content", "", "Other", vault, date_str="2026-01-01")
    assert "Porada" in os.path.basename(path)


def test_save_note_creates_folder(tmp_path):
    vault = str(tmp_path)
    path = save_note("content", "Meeting", "NewFolder", vault, date_str="2026-01-01")
    assert os.path.exists(path)
    assert "NewFolder" in path


def test_save_note_sanitizes_filename(vault):
    label = 'Invalid: Name? With <special> chars|here"'
    path = save_note("x", label, "Other", vault, date_str="2026-01-01")
    basename = os.path.basename(path)
    for char in r'\/:*?"<>|':
        assert char not in basename


def test_save_note_enforces_frontmatter_date(vault):
    note_md = "---\ndate:\ntype: meeting\ntags: [meeting]\n---\n\n# Meeting\n"
    path = save_note(note_md, "Meeting", "Other", vault, date_str="2025-05-22")
    content = open(path, encoding="utf-8").read()
    assert "date: 2025-05-22" in content


def test_save_note_overwrites_wrong_frontmatter_date(vault):
    note_md = "---\ndate: 2099-01-01\ntype: meeting\n---\n\n# Meeting\n"
    path = save_note(note_md, "Meeting", "Other", vault, date_str="2025-05-22")
    content = open(path, encoding="utf-8").read()
    assert "date: 2025-05-22" in content
    assert "2099-01-01" not in content


# ------------------------------------------------------------------
# save_transcript()
# ------------------------------------------------------------------

def test_save_transcript_empty_vault():
    result = save_transcript("hello", "Meeting", "", date_str="2026-01-01")
    assert result is None


def test_save_transcript_none_vault():
    result = save_transcript("hello", "Meeting", None, date_str="2026-01-01")
    assert result is None


def test_save_transcript_creates_file(vault):
    path = save_transcript("This is the transcript.", "Standup", vault, date_str="2026-04-01")
    assert path is not None
    assert os.path.exists(path)
    content = open(path, encoding="utf-8").read()
    assert "This is the transcript." in content


def test_save_transcript_uses_date_str(vault):
    path = save_transcript("text", "Meeting", vault, date_str="2025-07-04")
    assert "2025-07-04" in os.path.basename(path)


def test_save_transcript_sanitizes_filename(vault):
    label = "Meeting: Q1 <review>"
    path = save_transcript("text", label, vault, date_str="2026-01-01")
    basename = os.path.basename(path)
    for char in r'\/:*?"<>|':
        assert char not in basename


# ------------------------------------------------------------------
# Template placeholder substitution (inline logic test)
# ------------------------------------------------------------------

def test_save_note_path_contains_fusemark_meetings(vault):
    path = save_note("content", "Sprint", "Team", vault, date_str="2026-01-01")
    assert os.path.join("FuseMark", "Meetings", "Team") in path


def test_save_transcript_path_contains_fusemark_transcripts(vault):
    path = save_transcript("text", "Meeting", vault, date_str="2026-01-01")
    assert path is not None
    assert os.path.join("FuseMark", "Transcripts") in path


def test_template_placeholder_substitution():
    raw = "# {{title}}\n\nDate: {{date}}\n\n{{transcript}}"
    today = "2026-04-20"
    title = "Sprint Review"
    t_section = "[[FuseMark/Transcripts/2026-04-20 Sprint Review]]"
    result = (
        raw
        .replace("{{date}}", today)
        .replace("{{title}}", title)
        .replace("{{transcript}}", t_section)
    )
    assert "Sprint Review" in result
    assert "2026-04-20" in result
    assert "[[FuseMark/Transcripts" in result
    assert "{{" not in result
