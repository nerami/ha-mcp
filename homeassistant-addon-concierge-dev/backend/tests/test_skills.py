from concierge.config import Settings
from concierge.skills import (
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
