"""Assemble the Concierge agent: model + MCP toolsets + approval gating."""

from __future__ import annotations

import logging
import os

from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from concierge.config import Settings
from concierge.gating import approval_callback
from concierge.models import build_model
from concierge.skills import resolve_skills, skill_name

logger = logging.getLogger(__name__)

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

# Least-privilege env passthrough for the ha-mcp stdio child. The child is
# launched via the `ha-mcp` console script, so it genuinely needs PATH (to
# locate the script + its python), HOME, and common locale/runtime vars — but
# NOT Concierge's own secrets. We deliberately do NOT spread the full
# os.environ, which would leak CONCIERGE_API_KEY (the LLM provider key) and
# every other CONCIERGE_*/*_API_KEY secret into a process that never needs
# them. Only keys that are actually present in the parent are passed through.
_HAMCP_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TZ",
    "TERM",
    "PYTHONUNBUFFERED",
)


def _hamcp_env(settings: Settings) -> dict[str, str]:
    """Build the least-privilege env for the ha-mcp stdio subprocess.

    Passes through only the allowlisted runtime vars that exist in the parent,
    then adds the HA connection vars and the settings-UI sidecar toggle. No
    CONCIERGE_* / *_API_KEY secret is ever forwarded to the child.
    """
    env = {
        key: os.environ[key]
        for key in _HAMCP_ENV_ALLOWLIST
        if key in os.environ
    }
    env["HOMEASSISTANT_URL"] = settings.ha_url
    env["HOMEASSISTANT_TOKEN"] = settings.ha_token
    # Concierge serves its own UI; the bundled ha-mcp is a pure stdio tool
    # backend. Disable ha-mcp's stdio settings-UI sidecar — spawned fresh on
    # a real device it wedges the stdio MCP handshake (the sidecar child
    # holds/pollutes the stdout JSON-RPC channel), so the client init hangs
    # and the agent never starts. We never expose that UI, so skip it.
    env["HA_MCP_DISABLE_SETTINGS_UI"] = "1"
    return env


def _gated(toolset: MCPToolset, settings: Settings) -> AbstractToolset:
    if settings.auto_run_tools:
        return toolset
    return toolset.approval_required(approval_callback)


def build_hamcp_toolset(settings: Settings) -> AbstractToolset:
    """Bundled ha-mcp over stdio. Tools already carry ha_* names: no prefix."""
    transport = StdioTransport(command="ha-mcp", args=[], env=_hamcp_env(settings))
    return _gated(MCPToolset(transport, init_timeout=HAMCP_INIT_TIMEOUT), settings)


def build_skill_toolset(
    name: str, url: str, settings: Settings
) -> AbstractToolset:
    """One skill add-on over streamable HTTP, gated then namespaced."""
    return _gated(MCPToolset(url), settings).prefixed(name)


def _log_skill_summary(
    settings: Settings, resolved: list[tuple[str, str]]
) -> None:
    """Log a one-shot startup summary of which configured skills mounted."""
    mounted = [name for name, _ in resolved]
    logger.info("mounted %d skill(s): %s", len(mounted), mounted)
    mounted_names = set(mounted)
    unreachable = [
        entry
        for entry in settings.skills
        if entry.strip() and skill_name(entry) not in mounted_names
    ]
    if unreachable:
        logger.warning(
            "%d configured skill(s) not mounted (unreachable/unresolved): %s",
            len(unreachable),
            unreachable,
        )


async def build_agent(
    settings: Settings,
    *,
    toolsets: list[AbstractToolset] | None = None,
) -> Agent:
    """Build the agent; pass `toolsets` explicitly to skip discovery (tests)."""
    if toolsets is None:
        # STARTUP-ONLY: skills are resolved exactly once here, at agent
        # construction (process startup). There is no re-probe/refresh loop —
        # a skill add-on that boots slower than Concierge (cold-start race) or
        # restarts later is NOT picked up until Concierge itself is restarted.
        # Restart the add-on to mount new/late skills.
        resolved = await resolve_skills(settings)
        _log_skill_summary(settings, resolved)
        toolsets = [build_hamcp_toolset(settings)]
        for name, url in resolved:
            toolsets.append(build_skill_toolset(name, url, settings))
    return Agent(
        build_model(settings),
        instructions=SYSTEM_PROMPT,
        toolsets=toolsets,
        output_type=[str, DeferredToolRequests],
    )
