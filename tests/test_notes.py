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
