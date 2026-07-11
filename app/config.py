import contextlib
import json
import logging
import os
import shutil
import threading
import time

logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.environ["APPDATA"], "FuseMark")

SUPPORTED_LANGUAGES = [
    {"code": "cs",   "name": "Czech"},
    {"code": "en",   "name": "English"},
    {"code": "de",   "name": "German"},
    {"code": "fr",   "name": "French"},
    {"code": "pl",   "name": "Polish"},
    {"code": "sk",   "name": "Slovak"},
    {"code": "es",   "name": "Spanish"},
    {"code": "it",   "name": "Italian"},
    {"code": "auto", "name": "Auto-detect"},
]

WHISPER_MODEL_SIZES = {
    "large-v3-turbo": {"params": "809M", "disk_mb": 1500},
    "large-v3":       {"params": "1.5B",  "disk_mb": 3100},
}

DEFAULTS = {
    "vault_path": "",
    "output_device": None,
    "input_device": None,
    "whisper_model": "large-v3-turbo",
    "whisper_model_dir": os.path.join(
        os.environ.get("LOCALAPPDATA", DATA_DIR), "FuseMark", "models"),
    "log_level": "INFO",
    "default_template": "",
    "mode": "private",
    "transcription_provider": "whisper_local",
    "llm_provider": "anthropic",
    "language": "cs",
    "language_name": "Czech",
    "auto_delete_recordings": False,
    "max_recordings_gb": 5.0,
    "check_updates": True,
    "setup_complete": False,
    "ui_language": "en",
}

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")

_PROJECT_ROOT_CFG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

# Reentrant so a caller can hold lock() across a load-mutate-save sequence and still
# call save() (which also acquires this lock) without deadlocking itself.
_lock = threading.RLock()


@contextlib.contextmanager
def lock():
    """Hold the config lock across a load-mutate-save sequence so concurrent writers
    (e.g. the update-check background thread and a Settings save) can't drop each
    other's changes."""
    with _lock:
        yield


def load():
    os.makedirs(DATA_DIR, exist_ok=True)
    # One-time migration from project root (guard ensures this is skipped when CONFIG_PATH
    # is patched to a temp path in tests)
    _canonical = os.path.normcase(os.path.join(DATA_DIR, "config.json"))
    if os.path.normcase(CONFIG_PATH) == _canonical:
        if not os.path.exists(CONFIG_PATH) and os.path.exists(_PROJECT_ROOT_CFG):
            shutil.copy2(_PROJECT_ROOT_CFG, CONFIG_PATH)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            backup_path = f"{CONFIG_PATH}.corrupt-{int(time.time())}"
            try:
                shutil.copy2(CONFIG_PATH, backup_path)
                logger.warning("config.json was corrupt — backed up to %s, using defaults", backup_path)
            except OSError:
                logger.warning("config.json was corrupt and could not be backed up — using defaults")
            return dict(DEFAULTS)
        merged = {**DEFAULTS, **data}
        # Upgrade old model default to turbo
        if merged.get("whisper_model") == "large-v3":
            merged["whisper_model"] = "large-v3-turbo"
        return merged
    return dict(DEFAULTS)


def save(config):
    with _lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp_path = CONFIG_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, CONFIG_PATH)
