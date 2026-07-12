"""Assemble the Concierge agent: model + MCP toolsets + approval gating."""

from __future__ import annotations

import os

from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from concierge.config import Settings
from concierge.gating import approval_callback
from concierge.models import build_model
from concierge.skills import resolve_skills

SYSTEM_PROMPT = """\
You are Concierge, a helpful assistant for this Home Assistant home.

You control and inspect the home exclusively through your tools. When the
user mentions a device, area, or automation you do not have an exact id for,
first resolve it with whatever search/list/lookup tools are available (prefer
fuzzy or partial matching); only ask the user when no tool can resolve it.
Confirm what you did after acting. Be concise.
"""


def _gated(toolset: MCPToolset, settings: Settings) -> AbstractToolset:
    if settings.auto_run_tools:
        return toolset
    return toolset.approval_required(approval_callback)


def build_hamcp_toolset(settings: Settings) -> AbstractToolset:
    """Bundled ha-mcp over stdio. Tools already carry ha_* names: no prefix."""
    # The bundled ha-mcp runs over stdio in its "standard" mode, which refuses
    # to start unless BOTH HOMEASSISTANT_URL and HOMEASSISTANT_TOKEN hold real
    # (non-empty) values: it treats an empty/absent value as a fatal "missing
    # required variable" and exits, and a stdio subprocess exit crash-loops the
    # whole add-on at startup (its token-optional OAuth mode is a separate,
    # HTTP-only entrypoint we can't reach over stdio). Under Supervisor both
    # come from the core proxy URL + SUPERVISOR_TOKEN; without Supervisor
    # (local/dev, or a misconfigured install) the token is empty. Substitute a
    # harmless placeholder for any missing value so ha-mcp always starts and can
    # list its tools — ha-mcp connects to HA lazily per call, so a placeholder
    # never blocks startup and HA-backed calls simply fail at request time
    # (graceful degradation) instead of preventing the add-on from serving.
    env = {
        **os.environ,
        "HOMEASSISTANT_URL": settings.ha_url or "http://supervisor/core",
        "HOMEASSISTANT_TOKEN": settings.ha_token or "unauthenticated",
    }
    transport = StdioTransport(command="ha-mcp", args=[], env=env)
    return _gated(MCPToolset(transport), settings)


def build_skill_toolset(
    name: str, url: str, settings: Settings
) -> AbstractToolset:
    """One skill add-on over streamable HTTP, gated then namespaced."""
    return _gated(MCPToolset(url), settings).prefixed(name)


async def build_agent(
    settings: Settings,
    *,
    toolsets: list[AbstractToolset] | None = None,
) -> Agent:
    """Build the agent; pass `toolsets` explicitly to skip discovery (tests)."""
    if toolsets is None:
        toolsets = [build_hamcp_toolset(settings)]
        for name, url in await resolve_skills(settings):
            toolsets.append(build_skill_toolset(name, url, settings))
    return Agent(
        build_model(settings),
        instructions=SYSTEM_PROMPT,
        toolsets=toolsets,
        output_type=[str, DeferredToolRequests],
    )
