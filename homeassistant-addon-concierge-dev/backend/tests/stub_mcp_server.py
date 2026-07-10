"""Minimal annotated MCP server run over stdio in agent tests."""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("stub")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_temperature(room: str) -> str:
    """Get a room's temperature."""
    return f"{room}: 21C"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def delete_everything(target: str) -> str:
    """Destructively delete a target."""
    return f"deleted {target}"


if __name__ == "__main__":
    mcp.run()
