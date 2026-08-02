import os

import pytest
import app.prompts as pm


@pytest.fixture(autouse=True)
def _clear_prompt_cache():
    """_load()'s module-level cache must not leak resolved text between
    tests that reuse the same prompt `name` under different tmp_path dirs."""
    pm.clear_cache()
    yield
    pm.clear_cache()


# ------------------------------------------------------------------
# note_system.txt contract (#27 precedent guard)
# ------------------------------------------------------------------

def test_note_system_required_placeholders_unchanged():
    """#27's per-template instruction block is concatenated onto the
    resolved system prompt in app/llm/_common.py, deliberately without
    adding a 4th placeholder to note_system.txt — that would invalidate
    every existing user override of this prompt file. Locks the contract
    so a future change doesn't quietly reintroduce that break."""
    assert pm._PROMPTS["note_system"]["required"] == ["{lang_instruction}", "{template}", "{glossary}"]


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


def test_substitute_does_not_reexpand_injected_value():
    """The #31 bug: a value substituted for one key must not have its own
    literal {other_key} text picked up by that key's later substitution."""
    result = pm._substitute("{template} / {glossary}", template="Title: {glossary}", glossary="GLOSS")
    assert result == "Title: {glossary} / GLOSS"


def test_substitute_value_with_regex_backreference_syntax_is_literal():
    """Guards against ever switching back to a string-form re.sub, which
    would interpret \\1/\\g<0> in a user-controlled value."""
    result = pm._substitute("{x}", x=r"a\1b\g<0>")
    assert result == r"a\1b\g<0>"


def test_substitute_ignores_non_identifier_braces():
    result = pm._substitute("{a-b} and {a}", a="A")
    assert result == "{a-b} and A"


def test_build_note_system_title_containing_glossary_token_is_not_expanded(tmp_path, monkeypatch):
    """The real #31 scenario: a meeting title containing the literal text
    '{glossary}' must not have that later replaced by the real glossary."""
    monkeypatch.setattr(pm, "_user_dir", lambda: str(tmp_path / "prompts"))
    rendered_template = pm.build_note_template(date="2026-01-01", title="Q3 {glossary} review")
    result = pm.build_note_system(
        lang_instruction="en",
        template=rendered_template,
        glossary="REAL_GLOSSARY_JSON",
    )
    assert "Q3 {glossary} review" in result
    assert result.count("REAL_GLOSSARY_JSON") == 1


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
# _load — caching (#30)
# ------------------------------------------------------------------

def _bump_mtime(path, seconds_forward):
    import os
    st = os.stat(path)
    new_ns = st.st_mtime_ns + int(seconds_forward * 1_000_000_000)
    os.utime(path, ns=(new_ns, new_ns))


def test_load_reads_file_once_per_unchanged_state(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    (user_dir / "note_template.md").write_text("v1 {date} {title}", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))

    calls = []
    real_read = pm._read
    monkeypatch.setattr(pm, "_read", lambda p: (calls.append(p), real_read(p))[1])

    pm._load("note_template")
    pm._load("note_template")
    pm._load("note_template")

    user_reads = [c for c in calls if c.endswith("note_template.md") and str(user_dir) in c]
    assert len(user_reads) == 1


def test_load_picks_up_edit_without_restart(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    path = user_dir / "note_template.md"
    path.write_text("v1 {date} {title}", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))

    assert "v1" in pm._load("note_template")

    path.write_text("v2 {date} {title}", encoding="utf-8")
    _bump_mtime(path, 1)

    assert "v2" in pm._load("note_template")


def test_load_picks_up_newly_created_override(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))

    first = pm._load("note_template")
    assert "custom" not in first

    user_dir.mkdir()
    (user_dir / "note_template.md").write_text("custom {date} {title}", encoding="utf-8")

    assert "custom" in pm._load("note_template")


def test_load_picks_up_deleted_override(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    path = user_dir / "note_template.md"
    path.write_text("custom {date} {title}", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))

    assert "custom" in pm._load("note_template")

    path.unlink()

    assert "custom" not in pm._load("note_template")


def test_load_does_not_cache_invalid_override_as_valid(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    path = user_dir / "note_template.md"
    path.write_text("no placeholders at all", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))

    first = pm._load("note_template")
    assert "{date}" in first  # fell back to bundled

    path.write_text("fixed {date} {title}", encoding="utf-8")
    _bump_mtime(path, 1)

    assert "fixed" in pm._load("note_template")


def test_clear_cache_forces_reread(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    user_dir.mkdir()
    path = user_dir / "note_template.md"
    path.write_text("v1 {date} {title}", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))

    pm._load("note_template")

    # Same mtime/size — a naive cache miss check would still hit if it only
    # compared content, but overwriting with identical stats should still be
    # forced through by an explicit clear_cache() call.
    pm.clear_cache()
    calls = []
    real_read = pm._read
    monkeypatch.setattr(pm, "_read", lambda p: (calls.append(p), real_read(p))[1])
    pm._load("note_template")
    assert len(calls) == 1


def test_open_prompts_folder_clears_cache(tmp_path, monkeypatch):
    user_dir = tmp_path / "prompts"
    monkeypatch.setattr(pm, "_user_dir", lambda: str(user_dir))

    # Prime the cache against the bundled default (no override yet).
    first = pm._load("note_template")
    assert "custom" not in first

    with __import__("unittest.mock", fromlist=["patch"]).patch("os.startfile"):
        pm.open_prompts_folder()

    # open_prompts_folder() seeds a copy of the bundled default (not a
    # "custom" one), but the read must come from the newly-created user file,
    # not a stale cached bundled-file resolution.
    text = pm._load("note_template")
    assert os.path.exists(os.path.join(str(user_dir), "note_template.md"))
    assert text == first  # content is the same (seeded from the same bundled source)


def test_cache_respects_monkeypatched_user_dir_across_tests(tmp_path, monkeypatch):
    """Two different tmp_path-based user dirs for the same prompt name must
    not collide in the cache — this is really a regression guard for the
    autouse clear_cache fixture, not new behavior."""
    dir_a = tmp_path / "a"
    dir_a.mkdir()
    (dir_a / "note_template.md").write_text("from A {date} {title}", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(dir_a))
    assert "from A" in pm._load("note_template")

    dir_b = tmp_path / "b"
    dir_b.mkdir()
    (dir_b / "note_template.md").write_text("from B {date} {title}", encoding="utf-8")
    monkeypatch.setattr(pm, "_user_dir", lambda: str(dir_b))
    assert "from B" in pm._load("note_template")


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
