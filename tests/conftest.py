import pytest


@pytest.fixture
def tmp_vault(tmp_path):
    (tmp_path / "ObsiNote" / "Templates").mkdir(parents=True)
    (tmp_path / "ObsiNote" / "Meetings" / "Other").mkdir(parents=True)
    (tmp_path / "ObsiNote" / "Transcripts").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    import app.queue as q
    path = str(tmp_path / "jobs.db")
    monkeypatch.setattr(q, "DB_PATH", path)
    q.init_db()
    return path


@pytest.fixture
def flask_client(db_path, tmp_vault, monkeypatch, tmp_path):
    import app.config as cfg
    import app.server as srv
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save({**cfg.DEFAULTS, "vault_path": str(tmp_vault)})
    srv.app.config["TESTING"] = True
    with srv.app.test_client() as c:
        yield c
