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


def test_save_note_collision_uniquifies(tmp_vault):
    p1 = notes.save_note("first", "Standup", "Other", str(tmp_vault), date_str="2026-01-01")
    p2 = notes.save_note("second", "Standup", "Other", str(tmp_vault), date_str="2026-01-01")
    assert p1 != p2
    assert os.path.basename(p1) == "2026-01-01 Standup.md"
    assert os.path.basename(p2) == "2026-01-01 Standup (2).md"
    with open(p1, encoding="utf-8") as f:
        assert f.read() == "first"
    with open(p2, encoding="utf-8") as f:
        assert f.read() == "second"


def test_save_note_existing_path_overwrites_in_place(tmp_vault):
    p1 = notes.save_note("first", "Standup", "Other", str(tmp_vault), date_str="2026-01-01")
    p2 = notes.save_note(
        "updated", "Standup", "Other", str(tmp_vault), date_str="2026-01-01", existing_path=p1
    )
    assert p2 == p1
    with open(p1, encoding="utf-8") as f:
        assert f.read() == "updated"


def test_save_transcript_collision_uniquifies(tmp_vault):
    p1 = notes.save_transcript("first", "Standup", str(tmp_vault), date_str="2026-01-01")
    p2 = notes.save_transcript("second", "Standup", str(tmp_vault), date_str="2026-01-01")
    assert p1 != p2
    assert os.path.basename(p1) == "2026-01-01 Standup.md"
    assert os.path.basename(p2) == "2026-01-01 Standup (2).md"


def test_save_transcript_existing_path_overwrites_in_place(tmp_vault):
    p1 = notes.save_transcript("first", "Standup", str(tmp_vault), date_str="2026-01-01")
    p2 = notes.save_transcript(
        "updated", "Standup", str(tmp_vault), date_str="2026-01-01", existing_path=p1
    )
    assert p2 == p1
    with open(p1, encoding="utf-8") as f:
        assert "updated" in f.read()


# ------------------------------------------------------------------
# split_template_prompt() — per-template instruction block (#27)
# ------------------------------------------------------------------

def test_split_template_prompt_empty_string():
    assert notes.split_template_prompt("") == ("", "")


def test_split_template_prompt_no_block_returns_text_unchanged():
    text = "# {title}\n\n## Agenda\n## Decisions\n"
    assert notes.split_template_prompt(text) == (text, "")


def test_split_template_prompt_extracts_block():
    text = "# {title}\n\n<!-- fusemark:prompt\nBe terse.\n-->\n\n## Agenda\n"
    skeleton, instructions = notes.split_template_prompt(text)
    assert instructions == "Be terse."
    assert "fusemark:prompt" not in skeleton


def test_split_template_prompt_strips_block_from_skeleton():
    text = "# {title}\n<!-- fusemark:prompt\nBe terse.\n-->\n## Agenda\n"
    skeleton, _ = notes.split_template_prompt(text)
    assert "Be terse." not in skeleton
    assert "# {title}" in skeleton
    assert "## Agenda" in skeleton


def test_split_template_prompt_multiple_blocks_concatenated():
    text = (
        "# {title}\n"
        "<!-- fusemark:prompt\nBe terse.\n-->\n"
        "## Agenda\n"
        "<!-- fusemark:prompt\nExtract action items.\n-->\n"
        "## Decisions\n"
    )
    skeleton, instructions = notes.split_template_prompt(text)
    assert instructions == "Be terse. Extract action items."
    assert "fusemark:prompt" not in skeleton
    assert "## Agenda" in skeleton and "## Decisions" in skeleton


def test_split_template_prompt_case_insensitive_marker():
    text = "<!-- FuseMark:Prompt\nBe terse.\n-->\n## Agenda\n"
    _, instructions = notes.split_template_prompt(text)
    assert instructions == "Be terse."


def test_split_template_prompt_caps_length():
    long_instructions = "x" * 5000
    text = f"<!-- fusemark:prompt\n{long_instructions}\n-->\n## Agenda\n"
    _, instructions = notes.split_template_prompt(text)
    assert len(instructions) == notes.MAX_TEMPLATE_PROMPT_CHARS


def test_split_template_prompt_unterminated_block_left_alone():
    text = "# {title}\n<!-- fusemark:prompt\nBe terse.\n## Agenda\n"  # no closing -->
    skeleton, instructions = notes.split_template_prompt(text)
    assert skeleton == text
    assert instructions == ""


def test_split_template_prompt_does_not_strip_plain_html_comments():
    text = "# {title}\n<!-- just a regular comment -->\n## Agenda\n"
    skeleton, instructions = notes.split_template_prompt(text)
    assert skeleton == text
    assert instructions == ""
