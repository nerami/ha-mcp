"""Wire the real bundled ha-mcp over stdio and lock the annotation contract.

Uses a fake HOMEASSISTANT_URL: listing tools must not require a live HA.
This is the one live check the design flagged (spec §5.5/§11.3): the exact
key casing of MCP annotations as surfaced to our gating callback.
"""

from pydantic_ai.mcp import MCPToolset

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
    # the exact casing our gating reads: camelCase hints
    sample = annotated[0].annotations
    assert hasattr(sample, "readOnlyHint") and hasattr(sample, "destructiveHint")
