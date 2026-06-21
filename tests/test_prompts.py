import pytest
import app.prompts as pm


# ------------------------------------------------------------------
# _validate
# ------------------------------------------------------------------

def test_validate_passes_when_all_placeholders_present():
    pm._validate("Hello {name} and {other}", ["{name}", "{other}"])


def test_validate_raises_when_placeholder_missing():
    with pytest.raises(ValueError, match="missing required placeholders"):
        pm._validate("Hello {name}", ["{name}", "{other}"])


# ------------------------------------------------------------------
# _substitute
# ------------------------------------------------------------------

def test_substitute_replaces_placeholders():
    result = pm._substitute("Hello {name}!", name="World")
    assert result == "Hello World!"


def test_substitute_safe_with_braces_in_value():
    result = pm._substitute("Data: {json}", json='{"key": "value"}')
    assert result == 'Data: {"key": "value"}'


def test_substitute_leaves_unreferenced_placeholders():
    result = pm._substitute("{a} and {b}", a="A")
    assert result == "A and {b}"


def test_substitute_is_order_independent():
    # If a is replaced with {b}, it should not then be replaced by b="C"
    result = pm._substitute("{a} {b}", a="{b}", b="C")
    assert result == "{b} C"


# ------------------------------------------------------------------
# _load — bundled default fallback
# ------------------------------------------------------------------

def test_load_returns_bundled_when_no_user_override(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "_user_dir", lambda: str(tmp_path / "prompts"))
    text = pm._load("note_template")
    assert "{date}" in text
    assert "{title}" in text


def test_load_returns_user_override_when_valid(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    override = user_dir / "note_template.md"
    override.write_text("date={date} title={title} custom", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))
    text = pm._load("note_template")
    assert "custom" in text


def test_load_falls_back_to_bundled_when_user_override_invalid(tmp_path, monkeypatch, caplog):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    bad = user_dir / "note_template.md"
    bad.write_text("no placeholders here at all", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))
    import logging
    with caplog.at_level(logging.WARNING, logger="app.prompts"):
        text = pm._load("note_template")
    assert "{date}" in text
    assert "invalid" in caplog.text.lower() or "bundled" in caplog.text.lower()


# ------------------------------------------------------------------
# build_* helpers
# ------------------------------------------------------------------

def test_build_note_template_substitutes_date_and_title(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "_user_dir", lambda: str(tmp_path / "prompts"))
    result = pm.build_note_template(date="2026-01-01", title="Sprint Review")
    assert "2026-01-01" in result
    assert "Sprint Review" in result


def test_build_note_system_substitutes_all_placeholders(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "_user_dir", lambda: str(tmp_path / "prompts"))
    glossary_json = '{"terms": [{"canonical": "JIRA"}]}'
    result = pm.build_note_system(
        lang_instruction="Always write in Czech.",
        template="## Template",
        glossary=glossary_json,
    )
    assert "Always write in Czech." in result
    assert "## Template" in result
    assert glossary_json in result


def test_build_note_system_safe_with_json_braces(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "_user_dir", lambda: str(tmp_path / "prompts"))
    glossary_json = '{"terms": [{"canonical": "{weird}"}]}'
    result = pm.build_note_system(
        lang_instruction="en",
        template="tmpl",
        glossary=glossary_json,
    )
    assert glossary_json in result


def test_build_term_suggestion_substitutes_placeholders(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "_user_dir", lambda: str(tmp_path / "prompts"))
    result = pm.build_term_suggestion(
        transcript="We used JIRA and Confluence today.",
        existing_terms="JIRA",
    )
    assert "We used JIRA" in result
    assert "JIRA" in result


# ------------------------------------------------------------------
# _load — bundled missing raises a clear error (no silent crash on the
# note-generation path)
# ------------------------------------------------------------------

def test_load_raises_runtime_error_when_bundled_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "_user_dir", lambda: str(tmp_path / "prompts"))
    monkeypatch.setattr(pm, "_BUNDLED_DIR", str(tmp_path / "nonexistent"))
    with pytest.raises(RuntimeError, match="packaging error"):
        pm._load("note_template")


# ------------------------------------------------------------------
# validate_user_prompts
# ------------------------------------------------------------------

def test_validate_user_prompts_all_default_when_no_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(pm, "_user_dir", lambda: str(tmp_path / "prompts"))
    statuses = {e["name"]: e["status"] for e in pm.validate_user_prompts()}
    assert len(statuses) == len(pm._PROMPTS)
    assert set(statuses.values()) == {"default"}


def test_validate_user_prompts_reports_custom(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    (user_dir / "note_template.md").write_text("ok {date} {title}", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))
    by_name = {e["name"]: e for e in pm.validate_user_prompts()}
    assert by_name["note_template"]["status"] == "custom"


def test_validate_user_prompts_reports_invalid(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    (user_dir / "note_template.md").write_text("no placeholders", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))
    by_name = {e["name"]: e for e in pm.validate_user_prompts()}
    assert by_name["note_template"]["status"] == "invalid"
    assert by_name["note_template"]["error"]


# ------------------------------------------------------------------
# open_prompts_folder
# ------------------------------------------------------------------

def _patch_startfile():
    return __import__("unittest.mock", fromlist=["patch"]).patch("os.startfile")


def test_open_prompts_folder_creates_dir_and_copies_defaults(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))
    with _patch_startfile():
        pm.open_prompts_folder()
    assert user_dir.exists()
    files = list(user_dir.iterdir())
    assert len(files) == len(pm._PROMPTS)


def test_open_prompts_folder_does_not_overwrite_existing(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    existing = user_dir / "note_template.md"
    existing.write_text("my custom template {date} {title}", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))
    with _patch_startfile():
        pm.open_prompts_folder()
    assert existing.read_text(encoding="utf-8") == "my custom template {date} {title}"


def test_open_prompts_folder_seeds_missing_when_partially_populated(tmp_path, monkeypatch):
    # A non-empty folder must still receive any default it lacks (forward-compat
    # for prompts added later; also acts as delete-to-reset).
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    (user_dir / "note_template.md").write_text("custom {date} {title}", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))
    with _patch_startfile():
        pm.open_prompts_folder()
    seeded = {p.name for p in user_dir.iterdir()}
    assert seeded == {meta["file"] for meta in pm._PROMPTS.values()}
