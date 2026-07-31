"""LLM provider API key storage/status and stored-key connection test."""

from flask import Blueprint, jsonify, request

from app import config as cfg
from app.exceptions import LLMAuthError, LLMRateLimitError
from app.i18n import get_strings

bp = Blueprint("llm_keys", __name__)


@bp.route("/api/test-llm-stored", methods=["POST"])
def test_llm_stored():
    body = request.get_json(silent=True) or {}
    provider = body.get("provider", "")
    dispatch = {
        "anthropic": "app.llm.anthropic_provider",
        "openai":    "app.llm.openai_provider",
        "mistral":   "app.llm.mistral_provider",
    }
    if provider not in dispatch:
        return jsonify({"ok": False, "error": "Unknown provider"}), 400
    import importlib
    p = importlib.import_module(dispatch[provider])
    key = p._get_api_key()
    if not key:
        t = get_strings(cfg.load().get("ui_language", "en"))
        return jsonify({"ok": False, "error": t["msg_key_not_set"]})
    try:
        p.test_connection(key)
        return jsonify({"ok": True})
    except LLMAuthError as exc:
        return jsonify({"ok": False, "error": str(exc)})
    except LLMRateLimitError as exc:
        return jsonify({"ok": False, "error": str(exc)})


@bp.route("/api-key-status", methods=["GET"])
def route_api_key_status():
    """Return masked hint for each provider's stored key, without exposing the key."""
    import keyring
    providers = {
        "anthropic": ("FuseMark-Anthropic", "api_key"),
        "openai":    ("FuseMark-OpenAI",    "api_key"),
        "mistral":   ("FuseMark-Mistral",   "api_key"),
    }
    result = {}
    for provider, (service, username) in providers.items():
        key = keyring.get_password(service, username)
        if key and len(key) >= 8:
            result[provider] = key[:4] + "••••••••" + key[-4:]
        elif key:
            result[provider] = "••••••••"
        else:
            result[provider] = None
    return jsonify(result)


@bp.route("/api-key", methods=["POST"])
def route_api_key():
    data = request.get_json(silent=True) or {}
    key = data.get("key", "").strip()
    provider = data.get("provider", "anthropic")
    if not key:
        return jsonify({"error": "No key provided"}), 400
    if provider == "anthropic":
        from app.llm.anthropic_provider import set_api_key
    elif provider == "openai":
        from app.llm.openai_provider import set_api_key
    elif provider == "mistral":
        from app.llm.mistral_provider import set_api_key
    else:
        return jsonify({"error": f"Unknown provider: {provider}"}), 400
    set_api_key(key)
    return jsonify({"ok": True})
