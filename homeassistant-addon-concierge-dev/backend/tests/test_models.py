import logging
import os

from pydantic_ai.models.openai import OpenAIChatModel

from concierge import models
from concierge.config import Settings
from concierge.models import build_model, build_title_model


def test_native_provider_returns_string_form(monkeypatch) -> None:
    # setenv first so monkeypatch registers teardown restoration of the
    # original (unset) state; production code sets the env var and a bare
    # delenv(raising=False) on a missing var records nothing to restore.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sentinel")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    s = Settings(provider="anthropic", model="claude-sonnet-5", api_key="sk-x")
    assert build_model(s) == "anthropic:claude-sonnet-5"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-x"


def test_api_key_env_not_clobbered_when_empty(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "preset")
    s = Settings(provider="openai", model="gpt-5", api_key="")
    build_model(s)
    assert os.environ["OPENAI_API_KEY"] == "preset"


def test_base_url_builds_openai_compatible_model() -> None:
    s = Settings(model="qwen3", base_url="http://ollama.local:11434/v1", api_key="k")
    model = build_model(s)
    assert isinstance(model, OpenAIChatModel)


def test_title_model_uses_same_provider() -> None:
    s = Settings(provider="anthropic")
    assert build_title_model(s) == "anthropic:claude-haiku-4-5"


def test_unmapped_provider_warns_and_skips_api_key(monkeypatch, caplog) -> None:
    for env_var in models._API_KEY_ENV.values():
        monkeypatch.delenv(env_var, raising=False)
    s = Settings(provider="cerebras", model="some-model", api_key="sk-x")
    with caplog.at_level(logging.WARNING, logger="concierge.models"):
        assert build_model(s) == "cerebras:some-model"
    assert not any(env_var in os.environ for env_var in models._API_KEY_ENV.values())
    assert any(
        "no known API-key env var" in record.message for record in caplog.records
    )
