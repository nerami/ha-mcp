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
    env = {
        **os.environ,
        "HOMEASSISTANT_URL": settings.ha_url,
        "HOMEASSISTANT_TOKEN": settings.ha_token,
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
        # `build_model` may return a bare "provider:model" string (native
        # providers). Agent() eagerly resolves that string to a concrete
        # Model class, which imports the provider's SDK (e.g. `anthropic`)
        # even when every call site passes an explicit `model=` override (as
        # tests do with TestModel). Defer that resolution to first actual use
        # so constructing an Agent never requires every provider's optional
        # dependency to be installed.
        defer_model_check=True,
    )
