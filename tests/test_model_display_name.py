"""Tests for add_model.model_display_name.

The alias/format branches are pure. The OpenRouter fallback branch calls
fetch_model_info, which we monkeypatch so tests stay network-free.
"""
import add_model
from add_model import model_display_name


def test_empty_id():
    assert model_display_name("") == ""
    assert model_display_name(None) == ""


def test_id_without_slash_returned_verbatim():
    assert model_display_name("gpt-4o") == "gpt-4o"


def test_id_with_too_many_parts_returned_verbatim():
    assert model_display_name("a/b/c") == "a/b/c"


def test_alias_with_provider_name():
    assert model_display_name("anthropic/claude-sonnet-4.6") == "Anthropic Sonnet 4.6"
    assert model_display_name("google/gemini-2.5-flash") == "Gemini 2.5 Flash"
    assert model_display_name("openai/gpt-oss-120b-free") == "OpenAI OSS 120B Free"


def test_alias_is_case_insensitive():
    assert model_display_name("Anthropic/Claude-Sonnet-4.6") == "Anthropic Sonnet 4.6"


def test_fallback_uses_openrouter_name_and_dedupes_brand(monkeypatch):
    # No alias -> falls back to fetch_model_info. Name starts with a known
    # brand, so the provider name must NOT be prepended again.
    monkeypatch.setattr(add_model, "fetch_model_info", lambda mid: {"name": "Claude 99 Ultra"})
    assert model_display_name("anthropic/claude-99-ultra") == "Claude 99 Ultra"


def test_fallback_strips_provider_prefix(monkeypatch):
    monkeypatch.setattr(add_model, "fetch_model_info", lambda mid: {"name": "anthropic: Mega Model"})
    # "anthropic: " prefix stripped, then provider name prepended (not a brand)
    assert model_display_name("anthropic/mega-model") == "Anthropic Mega Model"


def test_fallback_prepends_provider_for_non_brand(monkeypatch):
    monkeypatch.setattr(add_model, "fetch_model_info", lambda mid: {"name": "Cool Model"})
    assert model_display_name("deepseek/some-thing") == "DeepSeek Cool Model"


def test_fallback_humanizes_id_when_no_name(monkeypatch):
    monkeypatch.setattr(add_model, "fetch_model_info", lambda mid: {"name": None})
    assert model_display_name("anthropic/foo-bar") == "Anthropic foo bar"


def test_unknown_provider_is_titlecased(monkeypatch):
    monkeypatch.setattr(add_model, "fetch_model_info", lambda mid: {"name": None})
    assert model_display_name("acmecorp/widget-x") == "Acmecorp widget x"
