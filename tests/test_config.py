import json
import os
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


def test_non_large_v3_model_not_upgraded(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    (tmp_path / "config.json").write_text(
        json.dumps({"whisper_model": "large-v3-turbo"}), encoding="utf-8"
    )
    result = cfg.load()
    assert result["whisper_model"] == "large-v3-turbo"


def test_supported_languages_contains_required_codes(tmp_path, monkeypatch):
    from app.config import SUPPORTED_LANGUAGES
    codes = {l["code"] for l in SUPPORTED_LANGUAGES}
    for code in ("cs", "en", "de", "fr", "auto"):
        assert code in codes, f"Missing language code: {code}"


def test_supported_languages_have_name_and_code():
    from app.config import SUPPORTED_LANGUAGES
    for entry in SUPPORTED_LANGUAGES:
        assert "code" in entry and "name" in entry
        assert entry["code"] and entry["name"]


def test_supported_languages_auto_detect_name():
    from app.config import SUPPORTED_LANGUAGES
    auto = next(l for l in SUPPORTED_LANGUAGES if l["code"] == "auto")
    assert auto["name"] == "Auto-detect"


def test_data_dir_is_under_appdata():
    import os
    import app.config as cfg
    appdata = os.environ.get("APPDATA", "")
    assert appdata, "APPDATA env var not set"
    assert cfg.DATA_DIR.startswith(appdata)
    assert "FuseMark" in cfg.DATA_DIR


def test_defaults_contain_p1_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    result = cfg.load()
    p1_keys = [
        "mode", "transcription_provider", "llm_provider",
        "language", "language_name", "whisper_model_dir",
        "auto_delete_recordings", "max_recordings_gb",
        "check_updates", "setup_complete",
    ]
    for key in p1_keys:
        assert key in result, f"Missing P1 key: {key}"


def test_save_is_atomic_no_leftover_tmp_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    cfg.save(dict(cfg.DEFAULTS))
    assert not (tmp_path / "config.json.tmp").exists()
    assert (tmp_path / "config.json").exists()


def test_load_corrupt_file_returns_defaults_and_backs_up(tmp_path, monkeypatch):
    cfg_path = tmp_path / "config.json"
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(cfg_path))
    cfg_path.write_text("{not valid json", encoding="utf-8")
    result = cfg.load()
    assert result == dict(cfg.DEFAULTS)
    backups = list(tmp_path.glob("config.json.corrupt-*"))
    assert len(backups) == 1
    with open(backups[0], encoding="utf-8") as f:
        assert f.read() == "{not valid json"


def test_lock_context_manager_allows_load_mutate_save(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    with cfg.lock():
        config = cfg.load()
        config["vault_path"] = "/locked/vault"
        cfg.save(config)
    assert cfg.load()["vault_path"] == "/locked/vault"


def test_lock_is_reentrant_for_nested_save_call(tmp_path, monkeypatch):
    # save() acquires the same lock internally — must not deadlock when called
    # from inside an already-held cfg.lock() block.
    monkeypatch.setattr(cfg, "CONFIG_PATH", str(tmp_path / "config.json"))
    with cfg.lock():
        cfg.save(dict(cfg.DEFAULTS))
    assert os.path.exists(str(tmp_path / "config.json"))
