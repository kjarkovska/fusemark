import json
import app.config as cfg


def test_load_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    result = cfg.load()
    assert result == dict(cfg.DEFAULTS)


def test_load_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    (tmp_path / "config.json").write_text(
        json.dumps({"vault_path": "/my/vault"}), encoding="utf-8"
    )
    result = cfg.load()
    assert result["vault_path"] == "/my/vault"
    assert result["whisper_model"] == cfg.DEFAULTS["whisper_model"]


def test_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    data = {**cfg.DEFAULTS, "vault_path": "/roundtrip/vault", "whisper_model": "small"}
    cfg.save(data)
    loaded = cfg.load()
    assert loaded["vault_path"] == "/roundtrip/vault"
    assert loaded["whisper_model"] == "small"


def test_unicode_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    path = "C:/Users/Kateřina/Dokumenty/Poznámky"
    cfg.save({**cfg.DEFAULTS, "vault_path": path})
    loaded = cfg.load()
    assert loaded["vault_path"] == path


def test_user_values_override_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    (tmp_path / "config.json").write_text(
        json.dumps({"whisper_model": "large-v3", "log_level": "INFO"}), encoding="utf-8"
    )
    result = cfg.load()
    # "large-v3" is silently upgraded to "large-v3-turbo" (P1 migration)
    assert result["whisper_model"] == "large-v3-turbo"
    assert result["log_level"] == "INFO"
