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
    # explicit chat model but no title model -> default title model still used
    assert Settings(model="x").effective_title_model == "claude-haiku-4-5"
