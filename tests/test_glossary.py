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
