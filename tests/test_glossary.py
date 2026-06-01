import os
import pytest
import app.glossary as gl


@pytest.fixture
def vault(tmp_path):
    (tmp_path / "ObsiNote").mkdir()
    return str(tmp_path)


@pytest.fixture
def patched_path(vault, monkeypatch):
    """Make glossary_path() return a deterministic temp path for functions that don't accept vault_path."""
    expected = os.path.join(vault, "ObsiNote", "Glossary.md")
    monkeypatch.setattr(gl, "glossary_path", lambda vp=None: expected)
    return expected


def _write_glossary(vault, rows):
    path = os.path.join(vault, "ObsiNote", "Glossary.md")
    lines = [
        "# ObsiNote Glossary",
        "",
        "| Term | Aliases | Context | Type |",
        "|------|---------|---------|------|",
    ]
    for r in rows:
        aliases = ", ".join(r.get("aliases", []))
        lines.append(f"| {r['canonical']} | {aliases} | {r.get('context','')} | {r.get('type','')} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# ------------------------------------------------------------------
# load()
# ------------------------------------------------------------------

def test_load_missing_file(vault):
    result = gl.load(vault)
    assert result == {"terms": []}


def test_load_parses_table(vault):
    _write_glossary(vault, [
        {"canonical": "Jira", "aliases": ["Yira", "Džira"], "context": "Projektový nástroj", "type": "Tool"},
        {"canonical": "PR", "aliases": ["pé er"], "context": "Pull request", "type": "abbreviation"},
    ])
    result = gl.load(vault)
    terms = result["terms"]
    assert len(terms) == 2
    assert terms[0]["canonical"] == "Jira"
    assert terms[0]["aliases"] == ["Yira", "Džira"]
    assert terms[0]["context"] == "Projektový nástroj"
    assert terms[0]["type"] == "Tool"
    assert terms[1]["canonical"] == "PR"
    assert terms[1]["aliases"] == ["pé er"]


def test_load_empty_aliases(vault):
    _write_glossary(vault, [
        {"canonical": "Scrum", "aliases": [], "context": "Agile framework", "type": "other"},
    ])
    terms = gl.load(vault)["terms"]
    assert terms[0]["aliases"] == []


# ------------------------------------------------------------------
# build_whisper_prompt()
# ------------------------------------------------------------------

def test_build_prompt_empty(patched_path):
    result = gl.build_whisper_prompt()
    assert result == ""


def test_build_prompt_formats_terms(vault, patched_path):
    _write_glossary(vault, [
        {"canonical": "Jira", "aliases": ["Yira", "Džira"], "context": "", "type": ""},
        {"canonical": "PR", "aliases": ["pé er"], "context": "", "type": ""},
    ])
    result = gl.build_whisper_prompt()
    assert "Jira" in result
    assert "Yira" in result
    assert "Džira" in result
    assert "PR" in result
    assert "pé er" in result


# ------------------------------------------------------------------
# add_terms()
# ------------------------------------------------------------------

def test_add_terms_new(vault, patched_path):
    new_term = {"canonical": "Slack", "aliases": [], "context": "Chat tool", "type": "product"}
    added = gl.add_terms([new_term])
    assert added == ["Slack"]
    terms = gl.load(vault)["terms"]
    assert any(t["canonical"] == "Slack" for t in terms)


def test_add_terms_dedup_case_insensitive(vault, patched_path):
    _write_glossary(vault, [
        {"canonical": "Jira", "aliases": [], "context": "", "type": ""},
    ])
    added = gl.add_terms([{"canonical": "jira", "aliases": [], "context": "", "type": ""}])
    assert added == []
    assert len(gl.load(vault)["terms"]) == 1


def test_add_terms_returns_added_names(vault, patched_path):
    terms = [
        {"canonical": "Slack", "aliases": [], "context": "", "type": ""},
        {"canonical": "Teams", "aliases": [], "context": "", "type": ""},
    ]
    added = gl.add_terms(terms)
    assert set(added) == {"Slack", "Teams"}


def test_add_terms_partial_dedup(vault, patched_path):
    _write_glossary(vault, [
        {"canonical": "Slack", "aliases": [], "context": "", "type": ""},
    ])
    added = gl.add_terms([
        {"canonical": "Slack", "aliases": [], "context": "", "type": ""},
        {"canonical": "Teams", "aliases": [], "context": "", "type": ""},
    ])
    assert added == ["Teams"]


# ------------------------------------------------------------------
# glossary_path()
# ------------------------------------------------------------------

def test_glossary_path_with_vault():
    result = gl.glossary_path("/my/vault")
    assert result == os.path.join("/my/vault", "ObsiNote", "Glossary.md")


def test_glossary_path_without_vault(monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "load", lambda: {"vault_path": ""})
    result = gl.glossary_path(None)
    assert result.endswith("Glossary.md")
    assert result.startswith(cfg.DATA_DIR)  # falls back to data directory (P1)


# ------------------------------------------------------------------
# load() — short/malformed rows
# ------------------------------------------------------------------

def test_load_skips_row_with_fewer_than_4_columns(vault):
    """A table row with < 4 pipe-delimited cells must be silently skipped."""
    path = os.path.join(vault, "ObsiNote", "Glossary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# ObsiNote Glossary\n\n")
        f.write("| Term | Aliases | Context | Type |\n")
        f.write("|------|---------|---------|------|\n")
        f.write("| Jira | Yira | Issue tracker | product |\n")  # valid
        f.write("| Short row |\n")                               # only 1 cell — skipped
    result = gl.load(vault)
    assert len(result["terms"]) == 1
    assert result["terms"][0]["canonical"] == "Jira"


# ------------------------------------------------------------------
# migrate_if_needed()
# ------------------------------------------------------------------

def test_migrate_if_needed_noop_when_no_json(tmp_path, monkeypatch):
    """No glossary.json present → function returns without creating Glossary.md."""
    glossary_md = tmp_path / "ObsiNote" / "Glossary.md"
    monkeypatch.setattr(gl, "_LEGACY_JSON_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setattr(gl, "glossary_path", lambda vp=None: str(glossary_md))

    gl.migrate_if_needed()

    assert not glossary_md.exists()


def test_migrate_if_needed_converts_json_to_md(tmp_path, monkeypatch):
    """Legacy glossary.json is converted to Glossary.md and then deleted."""
    import json

    legacy_json = tmp_path / "glossary.json"
    terms = [{"canonical": "JIRA", "aliases": ["Yira"], "context": "Issue tracker", "type": "product"}]
    legacy_json.write_text(json.dumps({"terms": terms}), encoding="utf-8")

    glossary_md = tmp_path / "ObsiNote" / "Glossary.md"
    monkeypatch.setattr(gl, "_LEGACY_JSON_PATH", str(legacy_json))
    monkeypatch.setattr(gl, "glossary_path", lambda vp=None: str(glossary_md))

    gl.migrate_if_needed()

    assert not legacy_json.exists()
    assert glossary_md.exists()
    loaded = gl.load(str(tmp_path))
    assert any(t["canonical"] == "JIRA" for t in loaded["terms"])


def test_migrate_if_needed_preserves_json_on_failure(tmp_path, monkeypatch):
    """If migration fails (bad JSON), the source glossary.json is preserved."""
    legacy_json = tmp_path / "glossary.json"
    legacy_json.write_text("not valid json", encoding="utf-8")

    glossary_md = tmp_path / "ObsiNote" / "Glossary.md"
    monkeypatch.setattr(gl, "_LEGACY_JSON_PATH", str(legacy_json))
    monkeypatch.setattr(gl, "glossary_path", lambda vp=None: str(glossary_md))

    gl.migrate_if_needed()  # must not raise

    assert legacy_json.exists()   # preserved because migration failed
    assert not glossary_md.exists()


# ------------------------------------------------------------------
# open_in_obsidian()
# ------------------------------------------------------------------

def test_open_in_obsidian_calls_startfile_with_obsidian_uri(tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    vault = str(tmp_path / "MyVault")
    with __import__("unittest.mock", fromlist=["patch"]).patch("os.startfile") as mock_start:
        gl.open_in_obsidian(vault_path=vault)
    mock_start.assert_called_once()
    uri = mock_start.call_args[0][0]
    assert uri.startswith("obsidian://")
    assert "MyVault" in uri
    assert "Glossary" in uri


def test_open_in_obsidian_no_vault_does_not_call_startfile(tmp_path, monkeypatch):
    import app.config as cfg
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "vault_path": ""})
    with __import__("unittest.mock", fromlist=["patch"]).patch("os.startfile") as mock_start:
        gl.open_in_obsidian(vault_path="")
    mock_start.assert_not_called()
