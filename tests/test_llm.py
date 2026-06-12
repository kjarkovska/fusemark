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

    mock_gen.assert_called_once_with("transcript", "Standup", "", "", "", "Czech", "")
    assert result == "# Note"


def test_generate_notes_dispatches_to_openai():
    from app.llm import generate_notes

    with patch("app.llm.cfg") as mock_cfg, \
         patch("app.llm.openai_provider.generate_notes", return_value="# Note") as mock_gen:
        mock_cfg.load.return_value = {"llm_provider": "openai"}
        generate_notes("transcript", language="English")

    mock_gen.assert_called_once()


def test_generate_notes_dispatches_to_mistral():
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
    from app.llm import suggest_glossary_terms

    with patch("app.llm.cfg") as mock_cfg, \
         patch("app.llm.anthropic_provider.suggest_glossary_terms", return_value=[]) as mock_s:
        mock_cfg.load.return_value = {"llm_provider": "anthropic"}
        result = suggest_glossary_terms("transcript")

    mock_s.assert_called_once_with("transcript")
    assert result == []


def test_suggest_glossary_terms_dispatches_to_openai():
    from app.llm import suggest_glossary_terms

    with patch("app.llm.cfg") as mock_cfg, \
         patch("app.llm.openai_provider.suggest_glossary_terms", return_value=[{"canonical": "OKR"}]) as mock_s:
        mock_cfg.load.return_value = {"llm_provider": "openai"}
        result = suggest_glossary_terms("transcript")

    mock_s.assert_called_once_with("transcript")
    assert result == [{"canonical": "OKR"}]


def test_suggest_glossary_terms_dispatches_to_mistral():
    from app.llm import suggest_glossary_terms

    with patch("app.llm.cfg") as mock_cfg, \
         patch("app.llm.mistral_provider.suggest_glossary_terms", return_value=[]) as mock_s:
        mock_cfg.load.return_value = {"llm_provider": "mistral"}
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

    mock_set.assert_called_once_with("FuseMark-Anthropic", "api_key", "sk-test")


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


def test_anthropic_suggest_rate_limit_raises_llm_rate_limit_error():
    import anthropic as ant
    from app.llm.anthropic_provider import suggest_glossary_terms

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ant.RateLimitError(
        message="rate limited", response=MagicMock(), body={}
    )
    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        with pytest.raises(LLMRateLimitError):
            suggest_glossary_terms("transcript")


def test_anthropic_suggest_auth_error_raises_llm_auth_error():
    import anthropic as ant
    from app.llm.anthropic_provider import suggest_glossary_terms

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ant.AuthenticationError(
        message="invalid key", response=MagicMock(), body={}
    )
    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        with pytest.raises(LLMAuthError, match="Invalid API key for Anthropic"):
            suggest_glossary_terms("transcript")


# ------------------------------------------------------------------
# Anthropic provider — generate_notes() optional fields
# ------------------------------------------------------------------

def test_anthropic_generate_notes_includes_optional_fields():
    """scratch_notes, extra_context, label, and folder must appear in the user message."""
    from app.llm.anthropic_provider import generate_notes

    mock_client = _make_anthropic_mock()
    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        generate_notes(
            "meeting transcript",
            label="Q4 Planning",
            folder="Strategy",
            scratch_notes="Budget approved",
            extra_context="Board meeting",
            language="English",
        )

    _, kwargs = mock_client.messages.create.call_args
    content = kwargs["messages"][0]["content"]
    assert "Q4 Planning" in content
    assert "Strategy" in content
    assert "Budget approved" in content
    assert "Board meeting" in content


def test_anthropic_date_str_used_in_template():
    from app.llm.anthropic_provider import generate_notes

    mock_client = _make_anthropic_mock()
    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        generate_notes("transcript", date_str="2025-05-22")

    _, kwargs = mock_client.messages.create.call_args
    assert "2025-05-22" in kwargs["system"]


def test_anthropic_date_str_defaults_to_today():
    from datetime import date
    from app.llm.anthropic_provider import generate_notes

    mock_client = _make_anthropic_mock()
    with patch("app.llm.anthropic_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.anthropic_provider.load_glossary", return_value={}), \
         patch("app.llm.anthropic_provider.anthropic.Anthropic", return_value=mock_client):
        generate_notes("transcript")

    _, kwargs = mock_client.messages.create.call_args
    assert date.today().isoformat() in kwargs["system"]


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

    mock_set.assert_called_once_with("FuseMark-OpenAI", "api_key", "sk-openai")


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

    mock_set.assert_called_once_with("FuseMark-Mistral", "api_key", "ms-key")


def test_mistral_rate_limit_raises_llm_rate_limit_error():
    from app.llm.mistral_provider import _handle_mistral_error

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


def test_mistral_unknown_exception_reraises():
    from app.llm.mistral_provider import _handle_mistral_error

    exc = RuntimeError("network failure")
    with pytest.raises(RuntimeError, match="network failure"):
        _handle_mistral_error(exc)


# ------------------------------------------------------------------
# OpenAI provider — suggest_glossary_terms()
# ------------------------------------------------------------------

def _make_openai_mock(content):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=content))]
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_resp
    return mock_client


def test_openai_suggest_returns_terms():
    from app.llm.openai_provider import suggest_glossary_terms

    terms = [{"canonical": "JIRA", "type": "product", "aliases": [], "context": "tracker"}]
    mock_client = _make_openai_mock(json.dumps(terms))
    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        result = suggest_glossary_terms("transcript")
    assert result == terms


def test_openai_suggest_invalid_json_returns_empty():
    from app.llm.openai_provider import suggest_glossary_terms

    mock_client = _make_openai_mock("not json at all")
    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        result = suggest_glossary_terms("transcript")
    assert result == []


def test_openai_suggest_non_list_json_returns_empty():
    from app.llm.openai_provider import suggest_glossary_terms

    mock_client = _make_openai_mock('{"key": "value"}')
    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        result = suggest_glossary_terms("transcript")
    assert result == []


def test_openai_suggest_strips_markdown_fences():
    from app.llm.openai_provider import suggest_glossary_terms

    terms = [{"canonical": "PR", "type": "abbreviation", "aliases": [], "context": "pull request"}]
    raw = "```json\n" + json.dumps(terms) + "\n```"
    mock_client = _make_openai_mock(raw)
    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        result = suggest_glossary_terms("transcript")
    assert result == terms


def test_openai_suggest_rate_limit_raises():
    import openai as oai
    from app.llm.openai_provider import suggest_glossary_terms

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = oai.RateLimitError(
        message="rate limited", response=MagicMock(), body={}
    )
    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        with pytest.raises(LLMRateLimitError):
            suggest_glossary_terms("transcript")


def test_openai_suggest_auth_error_raises():
    import openai as oai
    from app.llm.openai_provider import suggest_glossary_terms

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = oai.AuthenticationError(
        message="invalid key", response=MagicMock(), body={}
    )
    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        with pytest.raises(LLMAuthError):
            suggest_glossary_terms("transcript")


def test_openai_generate_includes_optional_fields_in_prompt():
    from app.llm.openai_provider import generate_notes

    mock_client = _make_openai_mock("# Note")
    with patch("app.llm.openai_provider.keyring.get_password", return_value="key"), \
         patch("app.llm.openai_provider.load_glossary", return_value={}), \
         patch("app.llm.openai_provider.OpenAI", return_value=mock_client):
        generate_notes("transcript", scratch_notes="rough", extra_context="ctx",
                       label="Standup", folder="Eng")

    _, kwargs = mock_client.chat.completions.create.call_args
    user_msg = kwargs["messages"][1]["content"]
    assert "rough" in user_msg
    assert "ctx" in user_msg
    assert "Standup" in user_msg
    assert "Eng" in user_msg


# ------------------------------------------------------------------
# Mistral provider — generate_notes() and suggest_glossary_terms()
# ------------------------------------------------------------------

def _make_mistral_mock(content="# Note"):
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(message=MagicMock(content=content))]
    mock_client = MagicMock()
    mock_client.chat.complete.return_value = mock_resp
    return mock_client


def test_mistral_generate_notes_returns_content():
    from app.llm.mistral_provider import generate_notes

    mock_client = _make_mistral_mock("# Meeting Note")
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        result = generate_notes("transcript", language="Czech")
    assert result == "# Meeting Note"


def test_mistral_generate_auto_detect_language():
    from app.llm.mistral_provider import generate_notes

    mock_client = _make_mistral_mock()
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        generate_notes("transcript", language="Auto-detect")

    _, kwargs = mock_client.chat.complete.call_args
    system_msg = kwargs["messages"][0]["content"]
    assert "Match the language of the transcript exactly." in system_msg


def test_mistral_generate_includes_optional_fields_in_prompt():
    from app.llm.mistral_provider import generate_notes

    mock_client = _make_mistral_mock()
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        generate_notes("transcript", scratch_notes="rough", extra_context="ctx",
                       label="Standup", folder="Eng")

    _, kwargs = mock_client.chat.complete.call_args
    user_msg = kwargs["messages"][1]["content"]
    assert "rough" in user_msg
    assert "ctx" in user_msg


def test_mistral_generate_rate_limit_raises():
    from app.llm.mistral_provider import generate_notes

    mock_client = MagicMock()
    exc = Exception("429 rate limit exceeded")
    exc.status_code = 429
    mock_client.chat.complete.side_effect = exc
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        with pytest.raises(LLMRateLimitError):
            generate_notes("transcript", language="Czech")


def test_mistral_generate_auth_error_raises():
    from app.llm.mistral_provider import generate_notes

    mock_client = MagicMock()
    exc = Exception("401 unauthorized")
    exc.status_code = 401
    mock_client.chat.complete.side_effect = exc
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        with pytest.raises(LLMAuthError):
            generate_notes("transcript", language="Czech")


def test_mistral_generate_unknown_exception_reraises():
    from app.llm.mistral_provider import generate_notes

    mock_client = MagicMock()
    mock_client.chat.complete.side_effect = RuntimeError("network failure")
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        with pytest.raises(RuntimeError, match="network failure"):
            generate_notes("transcript", language="Czech")


def test_mistral_suggest_returns_terms():
    from app.llm.mistral_provider import suggest_glossary_terms

    terms = [{"canonical": "K8s", "type": "abbreviation", "aliases": [], "context": "Kubernetes"}]
    mock_client = _make_mistral_mock(json.dumps(terms))
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        result = suggest_glossary_terms("transcript")
    assert result == terms


def test_mistral_suggest_invalid_json_returns_empty():
    from app.llm.mistral_provider import suggest_glossary_terms

    mock_client = _make_mistral_mock("not json")
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        result = suggest_glossary_terms("transcript")
    assert result == []


def test_mistral_suggest_strips_markdown_fences():
    from app.llm.mistral_provider import suggest_glossary_terms

    terms = [{"canonical": "CI", "type": "abbreviation", "aliases": [], "context": "Continuous integration"}]
    raw = "```json\n" + json.dumps(terms) + "\n```"
    mock_client = _make_mistral_mock(raw)
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        result = suggest_glossary_terms("transcript")
    assert result == terms


def test_mistral_suggest_rate_limit_raises():
    from app.llm.mistral_provider import suggest_glossary_terms

    mock_client = MagicMock()
    exc = Exception("429 rate limit exceeded")
    exc.status_code = 429
    mock_client.chat.complete.side_effect = exc
    with patch("app.llm.mistral_provider.keyring.get_password", return_value="ms-key"), \
         patch("app.llm.mistral_provider.load_glossary", return_value={}), \
         patch("app.llm.mistral_provider.Mistral", return_value=mock_client):
        with pytest.raises(LLMRateLimitError):
            suggest_glossary_terms("transcript")


# ------------------------------------------------------------------
# Provider contract — type alias + structural conformance
# ------------------------------------------------------------------

def test_generate_notes_callable_alias_is_defined():
    from app.llm import GenerateNotesCallable
    assert GenerateNotesCallable is not None


def test_suggest_terms_callable_alias_is_defined():
    from app.llm import SuggestTermsCallable
    assert SuggestTermsCallable is not None


def test_all_providers_have_generate_notes_function():
    import app.llm.anthropic_provider as ap
    import app.llm.openai_provider as op
    import app.llm.mistral_provider as mp
    for mod in (ap, op, mp):
        assert callable(getattr(mod, "generate_notes", None)), \
            f"{mod.__name__} missing generate_notes"


def test_all_providers_have_suggest_glossary_terms_function():
    import app.llm.anthropic_provider as ap
    import app.llm.openai_provider as op
    import app.llm.mistral_provider as mp
    for mod in (ap, op, mp):
        assert callable(getattr(mod, "suggest_glossary_terms", None)), \
            f"{mod.__name__} missing suggest_glossary_terms"
