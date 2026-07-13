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


# ha-mcp boots a heavy Python stack (fastmcp + the full tool registry) as a
# stdio subprocess. On a cold start on a slower target (e.g. an aarch64 HA
# Green with cold disk caches) that import can take far longer than fastmcp's
# short default client init timeout, so the MCP handshake times out and the
# whole agent fails to start. Give the handshake generous headroom: this only
# bounds startup, and a subprocess that actually dies still fails fast via a
# broken stdio pipe rather than waiting out the timeout.
HAMCP_INIT_TIMEOUT = 60.0


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
        # Concierge serves its own UI; the bundled ha-mcp is a pure stdio tool
        # backend. Disable ha-mcp's stdio settings-UI sidecar — spawned fresh on
        # a real device it wedges the stdio MCP handshake (the sidecar child
        # holds/pollutes the stdout JSON-RPC channel), so the client init hangs
        # and the agent never starts. We never expose that UI, so skip it.
        "HA_MCP_DISABLE_SETTINGS_UI": "1",
    }
    transport = StdioTransport(command="ha-mcp", args=[], env=env)
    return _gated(MCPToolset(transport, init_timeout=HAMCP_INIT_TIMEOUT), settings)


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
