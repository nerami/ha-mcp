"""Derive approval-required status from MCP safety annotations.

Policy: readOnlyHint -> auto-run; otherwise destructiveHint decides, and a
missing hint means gated (the MCP default for destructiveHint is true, and
fail-safe is the right default for un-annotated tools).
"""

from __future__ import annotations

from pydantic_ai.tools import ToolDefinition


def _get(annotations: object, key: str) -> object:
    if isinstance(annotations, dict):
        return annotations.get(key)
    return getattr(annotations, key, None)


def is_destructive(tool_def: ToolDefinition) -> bool:
    annotations = (tool_def.metadata or {}).get("annotations")
    if annotations is None:
        return True
    if _get(annotations, "readOnlyHint"):
        return False
    destructive = _get(annotations, "destructiveHint")
    return True if destructive is None else bool(destructive)


def approval_callback(
    ctx: object, tool_def: ToolDefinition, tool_args: dict[str, object]
) -> bool:
    """Signature expected by `toolset.approval_required(...)`."""
    return is_destructive(tool_def)
