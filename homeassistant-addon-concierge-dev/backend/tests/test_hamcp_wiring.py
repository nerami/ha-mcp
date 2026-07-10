"""Wire the real bundled ha-mcp over stdio and lock the annotation contract.

Uses a fake HOMEASSISTANT_URL: listing tools must not require a live HA.
This is the one live check the design flagged (spec §5.5/§11.3): the exact
key casing of MCP annotations as surfaced to our gating callback.
"""

from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

from concierge.agent import build_hamcp_toolset
from concierge.config import Settings


def settings() -> Settings:
    return Settings(
        ha_url="http://127.0.0.1:1", ha_token="fake-token", auto_run_tools=True
    )


async def test_hamcp_lists_tools_with_camel_case_annotations() -> None:
    # auto_run_tools=True -> raw MCPToolset (no approval wrapper), so we can
    # use the toolset's own client surface directly.
    toolset = build_hamcp_toolset(settings())
    assert isinstance(toolset, MCPToolset)
    async with toolset:
        tools = await toolset.list_tools()
    by_name = {t.name: t for t in tools}
    assert "ha_search" in by_name  # a stable, core ha-mcp tool

    annotated = [t for t in tools if t.annotations is not None]
    assert annotated, "expected ha-mcp to expose MCP annotations"
    # the exact casing our gating reads: camelCase hints, on a fixed tool so
    # a failure points somewhere stable.
    sample = by_name["ha_search"].annotations
    assert hasattr(sample, "readOnlyHint") and hasattr(sample, "destructiveHint")


async def test_gating_sees_camel_case_annotations_from_real_hamcp() -> None:
    """Lock the shape gating.py reads: ToolDefinition.metadata['annotations'].

    The approval callback fires with the pydantic-ai-mapped ToolDefinition
    BEFORE any tool execution, so gating the call keeps the unreachable
    fake HA out of the picture entirely.
    """
    captured: list[object] = []

    def spy(
        ctx: object, tool_def: ToolDefinition, tool_args: dict[str, object]
    ) -> bool:
        captured.append((tool_def.metadata or {}).get("annotations"))
        return True  # gate it: run pauses, tool never executes

    toolset = build_hamcp_toolset(settings())
    assert isinstance(toolset, MCPToolset)
    agent = Agent(
        TestModel(call_tools=["ha_search"]),
        toolsets=[toolset.approval_required(spy)],
        output_type=[str, DeferredToolRequests],
    )
    result = await agent.run("search for lights")
    assert isinstance(result.output, DeferredToolRequests)  # paused, not executed
    [annotations] = captured
    assert isinstance(annotations, dict)
    assert annotations.get("readOnlyHint") is True  # ha_search is read-only
