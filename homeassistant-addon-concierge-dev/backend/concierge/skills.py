"""Resolve skill add-on slugs to MCP endpoints via Supervisor DNS.

A skill is a sibling add-on named `ha-concierge-skill-<slug>` running a
FastMCP streamable-HTTP server on :9000/mcp. Supervisor DNS names add-ons
`<repo-prefix>-<slug-with-dashes>`; we derive the prefix from our own
hostname, so no Supervisor API privilege is needed. A full http(s) URL entry
is used verbatim (cross-repo escape hatch). Unreachable skills are probed
with bounded retries and skipped so one bad skill never sinks the rest.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable

from pydantic_ai.mcp import MCPToolset

from concierge.config import Settings

logger = logging.getLogger(__name__)

SKILL_PORT = 9000
_SKILL_INFIX = "ha-concierge-skill-"
# Both flavors, dev first so the longer suffix wins.
_OWN_SUFFIXES = ("-ha-mcp-concierge-dev", "-ha-mcp-concierge")
_PROBE_ATTEMPTS = 3
_PROBE_DELAY_SECONDS = 1.5


def repo_prefix(hostname: str) -> str | None:
    for suffix in _OWN_SUFFIXES:
        if hostname.endswith(suffix):
            return hostname[: -len(suffix)] or None
    return None


def _is_url(entry: str) -> bool:
    return entry.startswith(("http://", "https://"))


def skill_endpoint(entry: str, prefix: str | None) -> str | None:
    entry = entry.strip()
    if not entry:
        return None
    if _is_url(entry):
        return entry
    if not prefix:
        return None
    return f"http://{prefix}-{_SKILL_INFIX}{entry}:{SKILL_PORT}/mcp"


def skill_name(entry: str) -> str:
    if _is_url(entry):
        host = entry.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
        return host.replace("-", "_")
    return entry.strip().replace("-", "_")


async def probe_endpoint(url: str) -> bool:
    """Connect (and disconnect) an MCP toolset, retrying briefly."""
    for attempt in range(_PROBE_ATTEMPTS):
        try:
            async with MCPToolset(url):
                return True
        except Exception as exc:  # noqa: BLE001 - degrade per-skill, never crash
            logger.warning(
                "skill endpoint %s unreachable (attempt %d/%d): %s",
                url,
                attempt + 1,
                _PROBE_ATTEMPTS,
                exc,
            )
            if attempt < _PROBE_ATTEMPTS - 1:
                await asyncio.sleep(_PROBE_DELAY_SECONDS)
    return False


async def resolve_skills(
    settings: Settings,
    *,
    probe: Callable[[str], Awaitable[bool]] = probe_endpoint,
    hostname: str | None = None,
) -> list[tuple[str, str]]:
    """Return (name, url) for every configured, reachable skill."""
    prefix = repo_prefix(hostname or socket.gethostname())
    pairs: list[tuple[str, str]] = []
    for entry in settings.skills:
        url = skill_endpoint(entry, prefix)
        if url is None:
            if entry.strip():
                logger.warning(
                    "skill %r cannot be resolved (no repo prefix); "
                    "list it as a full http(s)://.../mcp URL instead",
                    entry,
                )
            continue
        if await probe(url):
            pairs.append((skill_name(entry), url))
    return pairs
