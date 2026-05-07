import json
from unittest.mock import MagicMock, patch

import pytest

from app.exceptions import LLMAuthError, LLMRateLimitError


# ------------------------------------------------------------------
# Dispatcher — generate_notes()
# ------------------------------------------------------------------

def test_generate_notes_unknown_provider_raises():
    from app.llm import generate_notes

    with patch("app.llm.cfg") as mock_cfg:
        mock_cfg.load.return_value = {"llm_provider": "grok"}
        with pytest.raises(ValueError, match="Unknown llm_provider"):
            generate_notes("transcript")


def test_generate_notes_dispatches_to_anthropic():
    from app.llm import generate_notes

    with patch("app.llm.cfg") as mock_cfg, \
         patch("app.llm.anthropic_provider.generate_notes", return_value="# Note") as mock_gen:
        mock_cfg.load.return_value = {"llm_provider": "anthropic"}
        result = generate_notes("transcript", label="Standup", language="Czech")

    mock_gen.assert_called_once_with("transcript", "Standup", "", "", "", "Czech")
    assert result == "# Note"


def test_generate_notes_dispatches_to_openai():
    import app.llm.openai_provider  # ensure module is registered as package attribute
    from app.llm import generate_notes

    with patch("app.llm.cfg") as mock_cfg, \
         patch("app.llm.openai_provider.generate_notes", return_value="# Note") as mock_gen:
        mock_cfg.load.return_value = {"llm_provider": "openai"}
        generate_notes("transcript", language="English")

    mock_gen.assert_called_once()


def test_generate_notes_dispatches_to_mistral():
    import app.llm.mistral_provider  # ensure module is registered as package attribute
    from app.llm import generate_notes

    with patch("app.llm.cfg") as mock_cfg, \
         patch("app.llm.mistral_provider.generate_notes", return_value="# Note") as mock_gen:
        mock_cfg.load.return_value = {"llm_provider": "mistral"}
        generate_notes("transcript", language="French")

    mock_gen.assert_called_once()


# ------------------------------------------------------------------
# Dispatcher — suggest_glossary_terms()
# ------------------------------------------------------------------

def test_suggest_glossary_terms_unknown_provider_raises():
    from app.llm import suggest_glossary_terms

    with patch("app.llm.cfg") as mock_cfg:
        mock_cfg.load.return_value = {"llm_provider": "grok"}
        with pytest.raises(ValueError, match="Unknown llm_provider"):
            suggest_glossary_terms("transcript")


def test_suggest_glossary_terms_dispatches_to_anthropic():
    import app.llm.anthropic_provider  # ensure module is registered as package attribute
    from app.llm import suggest_glossary_terms

    with patch("app.llm.cfg") as mock_cfg, \
         patch("app.llm.anthropic_provider.suggest_glossary_terms", return_value=[]) as mock_s:
        mock_cfg.load.return_value = {"llm_provider": "anthropic"}
        result = suggest_glossary_terms("transcript")

    mock_s.assert_called_once_with("transcript")
    assert result == []


# ------------------------------------------------------------------
# Anthropic provider — API key
# ------------------------------------------------------------------

def test_anthropic_missing_key_raises_llm_auth_error():
    from app.llm.anthropic_provider import _get_api_key

    with patch("app.llm.anthropic_provider.keyring.get_password", return_value=None):
        with pytest.raises(LLMAuthError):
            _get_api_key()


def test_anthropic_set_api_key_writes_to_keyring():
    from app.llm.anthropic_provider import set_api_key

    with patch("app.llm.anthropic_provider.keyring.set_password") as mock_set:
        set_api_key("sk-test")

    mock_set.assert_called_once_with("ObsiNote-Anthropic", "api_key", "sk-test")


# ------------------------------------------------------------------
# Anthropic provider — generate_notes()
# ------------------------------------------------------------------

def _make_anthropic_mock(text="# Meeting Note"):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg
    return mock_client


def test_anthropic_auto_detect_uses_match_instruction():
    import anthropic as ant
    from app.llm.anthropic_provider import generate_notes

    mock_client = _make_anthropic_mock()
    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        generate_notes("transcript", language="Auto-detect")

    _, kwargs = mock_client.messages.create.call_args
    assert "Match the language of the transcript exactly." in kwargs["system"]


def test_anthropic_explicit_language_uses_always_write():
    from app.llm.anthropic_provider import generate_notes

    mock_client = _make_anthropic_mock()
    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        generate_notes("transcript", language="Czech")

    _, kwargs = mock_client.messages.create.call_args
    assert "Always write in Czech." in kwargs["system"]


def test_anthropic_rate_limit_raises_llm_rate_limit_error():
    import anthropic as ant
    from app.llm.anthropic_provider import generate_notes

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ant.RateLimitError(
        message="rate limited", response=MagicMock(), body={}
    )
    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        with pytest.raises(LLMRateLimitError):
            generate_notes("transcript", language="Czech")


def test_anthropic_auth_error_raises_llm_auth_error():
    import anthropic as ant
    from app.llm.anthropic_provider import generate_notes

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ant.AuthenticationError(
        message="invalid key", response=MagicMock(), body={}
    )
    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        with pytest.raises(LLMAuthError, match="Invalid API key for Anthropic"):
            generate_notes("transcript", language="Czech")


# ------------------------------------------------------------------
# Anthropic provider — suggest_glossary_terms()
# ------------------------------------------------------------------

def test_anthropic_suggest_strips_markdown_fences():
    from app.llm.anthropic_provider import suggest_glossary_terms

    terms = [{"canonical": "JIRA", "aliases": [], "context": "Issue tracker", "type": "product"}]
    raw = "```json\n" + json.dumps(terms) + "\n```"

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=raw)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        result = suggest_glossary_terms("transcript")

    assert result == terms


def test_anthropic_suggest_invalid_json_returns_empty():
    from app.llm.anthropic_provider import suggest_glossary_terms

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not valid json at all")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        result = suggest_glossary_terms("transcript")

    assert result == []


def test_anthropic_suggest_non_list_json_returns_empty():
    from app.llm.anthropic_provider import suggest_glossary_terms

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text='{"key": "value"}')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        result = suggest_glossary_terms("transcript")

    assert result == []


# ------------------------------------------------------------------
# OpenAI provider — key and dispatch
# ------------------------------------------------------------------

def test_openai_missing_key_raises_llm_auth_error():
    from app.llm.openai_provider import _get_api_key

    with patch("app.llm.openai_provider.keyring.get_password", return_value=None):
        with pytest.raises(LLMAuthError):
            _get_api_key()


def test_openai_set_api_key_writes_to_keyring():
    from app.llm.openai_provider import set_api_key

    with patch("app.llm.openai_provider.keyring.set_password") as mock_set:
        set_api_key("sk-openai")

    mock_set.assert_called_once_with("ObsiNote-OpenAI", "api_key", "sk-openai")


def test_openai_auto_detect_language_instruction():
    from app.llm.openai_provider import generate_notes

    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content="# Note"))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp

    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        generate_notes("transcript", language="Auto-detect")

    _, kwargs = mock_client.chat.completions.create.call_args
    system_content = kwargs["messages"][0]["content"]
    assert "Match the language of the transcript exactly." in system_content


def test_openai_rate_limit_raises_llm_rate_limit_error():
    import openai as oai
    from app.llm.openai_provider import generate_notes

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = oai.RateLimitError(
        message="rate limited", response=MagicMock(), body={}
    )

    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        with pytest.raises(LLMRateLimitError):
            generate_notes("transcript", language="English")


def test_openai_auth_error_raises_llm_auth_error():
    import openai as oai
    from app.llm.openai_provider import generate_notes

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = oai.AuthenticationError(
        message="invalid key", response=MagicMock(), body={}
    )

    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        with pytest.raises(LLMAuthError, match="Invalid API key for OpenAI"):
            generate_notes("transcript", language="English")


# ------------------------------------------------------------------
# Mistral provider — key and dispatch
# ------------------------------------------------------------------

def test_mistral_missing_key_raises_llm_auth_error():
    from app.llm.mistral_provider import _get_api_key

    with patch("app.llm.mistral_provider.keyring.get_password", return_value=None):
        with pytest.raises(LLMAuthError):
            _get_api_key()


def test_mistral_set_api_key_writes_to_keyring():
    from app.llm.mistral_provider import set_api_key

    with patch("app.llm.mistral_provider.keyring.set_password") as mock_set:
        set_api_key("ms-key")

    mock_set.assert_called_once_with("ObsiNote-Mistral", "api_key", "ms-key")


def test_mistral_rate_limit_raises_llm_rate_limit_error():
    from app.llm.mistral_provider import generate_notes, _handle_mistral_error

    exc = Exception("429 rate limit exceeded")
    exc.status_code = 429

    with pytest.raises(LLMRateLimitError):
        _handle_mistral_error(exc)


def test_mistral_auth_error_raises_llm_auth_error():
    from app.llm.mistral_provider import _handle_mistral_error

    exc = Exception("401 unauthorized")
    exc.status_code = 401

    with pytest.raises(LLMAuthError):
        _handle_mistral_error(exc)
