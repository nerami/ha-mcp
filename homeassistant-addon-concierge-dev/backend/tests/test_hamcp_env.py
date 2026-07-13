"""Least-privilege env for the bundled ha-mcp stdio subprocess.

The child is launched via the `ha-mcp` console script, so it needs PATH and a
few runtime vars — but must NOT inherit Concierge's own secrets (the LLM
provider key lives in CONCIERGE_API_KEY). Spreading the full os.environ leaked
every parent var into the child; these tests lock the curated allowlist.
"""

import pytest

from concierge.agent import _hamcp_env
from concierge.config import Settings


def _settings() -> Settings:
    return Settings(ha_url="http://ha:8123", ha_token="secret-token")


def test_env_carries_ha_connection_and_sidecar_toggle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    env = _hamcp_env(_settings())
    assert env["HOMEASSISTANT_URL"] == "http://ha:8123"
    assert env["HOMEASSISTANT_TOKEN"] == "secret-token"
    assert env["HA_MCP_DISABLE_SETTINGS_UI"] == "1"
    # PATH is required to locate the ha-mcp console script + its python.
    assert env["PATH"] == "/usr/bin:/bin"


def test_env_excludes_concierge_and_api_key_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("CONCIERGE_API_KEY", "sk-provider-secret")
    monkeypatch.setenv("CONCIERGE_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-other-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    env = _hamcp_env(_settings())
    assert "CONCIERGE_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    # No CONCIERGE_* var leaks through at all.
    assert not any(key.startswith("CONCIERGE_") for key in env)


def test_env_passes_through_only_present_allowlisted_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("TZ", "UTC")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    env = _hamcp_env(_settings())
    assert env["LANG"] == "en_US.UTF-8"
    assert env["TZ"] == "UTC"
    # Allowlisted but absent in the parent -> not fabricated in the child.
    assert "LC_ALL" not in env
    assert "TERM" not in env
