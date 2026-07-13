import asyncio

import pytest

from concierge.config import Settings
from concierge.skills import (
    _PROBE_TIMEOUT_SECONDS,
    probe_endpoint,
    repo_prefix,
    resolve_skills,
    skill_endpoint,
    skill_name,
)


def test_repo_prefix_derivation() -> None:
    assert repo_prefix("local-ha-mcp-concierge-dev") == "local"
    assert repo_prefix("local-ha-mcp-concierge") == "local"
    assert repo_prefix("a1b2c3d4-ha-mcp-concierge") == "a1b2c3d4"
    assert repo_prefix("something-else") is None


def test_skill_endpoint_from_slug() -> None:
    assert (
        skill_endpoint("pixoo", "local")
        == "http://local-ha-concierge-skill-pixoo:9000/mcp"
    )
    assert skill_endpoint("pixoo", None) is None
    assert skill_endpoint("", "local") is None


def test_full_url_passthrough() -> None:
    url = "http://elsewhere:9000/mcp"
    assert skill_endpoint(url, None) == url


def test_skill_name() -> None:
    assert skill_name("pixoo-max") == "pixoo_max"
    assert skill_name("http://divoom-thing:9000/mcp") == "divoom_thing"


async def test_resolve_skills_skips_unreachable() -> None:
    async def probe(url: str) -> bool:
        return "good" in url

    s = Settings(skills=["good", "bad", "http://good-remote:9000/mcp"])
    pairs = await resolve_skills(s, probe=probe, hostname="local-ha-mcp-concierge-dev")
    assert pairs == [
        ("good", "http://local-ha-concierge-skill-good:9000/mcp"),
        ("good_remote", "http://good-remote:9000/mcp"),
    ]


async def test_resolve_skills_no_prefix_skips_bare_slugs() -> None:
    async def probe(url: str) -> bool:
        return True

    s = Settings(skills=["pixoo"])
    assert await resolve_skills(s, probe=probe, hostname="weird-host") == []


async def test_resolve_skills_dedupes_normalized_name_collision() -> None:
    # "my-skill" and "my_skill" both normalize to prefix "my_skill"; the second
    # must be skipped so two toolsets aren't mounted under the same prefix.
    async def probe(url: str) -> bool:
        return True

    s = Settings(skills=["my-skill", "my_skill"])
    pairs = await resolve_skills(
        s, probe=probe, hostname="local-ha-mcp-concierge-dev"
    )
    assert pairs == [
        ("my_skill", "http://local-ha-concierge-skill-my-skill:9000/mcp"),
    ]


class _HangingToolset:
    """MCPToolset stand-in whose connect never completes."""

    def __init__(self, url: str) -> None:
        self._url = url

    async def __aenter__(self) -> "_HangingToolset":
        await asyncio.sleep(3600)  # simulate a half-open server
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


async def test_probe_endpoint_times_out_on_hang(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A half-open server that accepts the connection but never handshakes must
    # not hang the probe: each attempt is bounded by _PROBE_TIMEOUT_SECONDS.
    monkeypatch.setattr("concierge.skills.MCPToolset", _HangingToolset)
    monkeypatch.setattr("concierge.skills._PROBE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr("concierge.skills._PROBE_ATTEMPTS", 2)
    monkeypatch.setattr("concierge.skills._PROBE_DELAY_SECONDS", 0.0)

    result = await asyncio.wait_for(
        probe_endpoint("http://hang:9000/mcp"), timeout=2.0
    )
    assert result is False


async def test_resolve_skills_skips_hanging_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # End to end: a hanging endpoint times out per attempt and is skipped
    # rather than sinking resolution (uses the real probe_endpoint).
    monkeypatch.setattr("concierge.skills.MCPToolset", _HangingToolset)
    monkeypatch.setattr("concierge.skills._PROBE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr("concierge.skills._PROBE_ATTEMPTS", 1)
    monkeypatch.setattr("concierge.skills._PROBE_DELAY_SECONDS", 0.0)

    s = Settings(skills=["pixoo"])
    pairs = await asyncio.wait_for(
        resolve_skills(s, hostname="local-ha-mcp-concierge-dev"), timeout=2.0
    )
    assert pairs == []


def test_probe_timeout_constant_is_bounded() -> None:
    assert 0 < _PROBE_TIMEOUT_SECONDS <= 30
