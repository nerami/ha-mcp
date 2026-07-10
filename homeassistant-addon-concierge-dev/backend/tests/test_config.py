from pathlib import Path

from concierge.config import Settings, load_settings


def test_defaults() -> None:
    s = Settings()
    assert s.provider == "anthropic"
    assert s.model == "claude-sonnet-5"
    assert s.title_model is None
    assert s.auto_run_tools is False
    assert s.skills == []
    assert s.data_dir == Path("/data")
    assert s.port == 8098
    assert s.tracing is False


def test_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("CONCIERGE_MODEL", "gpt-5")
    monkeypatch.setenv("CONCIERGE_PROVIDER", "openai")
    monkeypatch.setenv("CONCIERGE_AUTO_RUN_TOOLS", "true")
    monkeypatch.setenv("CONCIERGE_SKILLS", '["pixoo","http://x:9000/mcp"]')
    s = load_settings()
    assert (s.provider, s.model) == ("openai", "gpt-5")
    assert s.auto_run_tools is True
    assert s.skills == ["pixoo", "http://x:9000/mcp"]


def test_effective_title_model_falls_back() -> None:
    assert Settings().effective_title_model == "claude-haiku-4-5"
    assert Settings(title_model="m").effective_title_model == "m"
    # anthropic provider, no base_url, no explicit chat model -> default title model
    assert Settings(model="x").effective_title_model == "claude-haiku-4-5"


def test_effective_title_model_falls_back_to_chat_model_on_other_providers() -> None:
    # non-anthropic provider: DEFAULT_TITLE_MODEL ("claude-haiku-4-5") would be
    # unresolvable, so fall back to the configured chat model instead.
    assert (
        Settings(provider="openai", model="gpt-5").effective_title_model == "gpt-5"
    )
    assert (
        Settings(provider="google", model="gemini-2.5-pro").effective_title_model
        == "gemini-2.5-pro"
    )
    # anthropic provider but a custom base_url: still not the native API.
    assert (
        Settings(
            provider="anthropic", model="qwen3", base_url="http://x:9000/v1"
        ).effective_title_model
        == "qwen3"
    )
