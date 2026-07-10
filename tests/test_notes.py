import os

import app.notes as notes


def test_load_template_reads_existing(tmp_vault):
    tdir = tmp_vault / "FuseMark" / "Templates"
    (tdir / "Meeting.md").write_text("hello", encoding="utf-8")
    assert notes.load_template(str(tmp_vault), "Meeting") == "hello"


def test_load_template_missing_returns_none(tmp_vault):
    assert notes.load_template(str(tmp_vault), "Nope") is None


def test_load_template_rejects_path_traversal(tmp_vault):
    # A file outside the Templates dir must not be reachable via "../" in the name.
    (tmp_vault / "secret.md").write_text("top secret", encoding="utf-8")
    # basename() collapses the traversal to "secret", which doesn't exist under Templates.
    assert notes.load_template(str(tmp_vault), "../../secret") is None


def test_save_note_rejects_path_traversal(tmp_vault, tmp_path):
    # A traversal-y folder must collapse to its basename, staying inside Meetings.
    out_path = notes.save_note("note body", "Label", "../../escape", str(tmp_vault))
    meetings_dir = tmp_vault / "FuseMark" / "Meetings"
    assert out_path == str(meetings_dir / "escape" / "2026-07-10 Label.md") or \
        os.path.dirname(out_path) == str(meetings_dir / "escape")
    assert not (tmp_path / "escape").exists()


def test_save_note_bare_dotdot_folder_falls_back_to_other(tmp_vault):
    out_path = notes.save_note("note body", "Label", "..", str(tmp_vault))
    assert os.path.join("Meetings", "Other") in out_path
