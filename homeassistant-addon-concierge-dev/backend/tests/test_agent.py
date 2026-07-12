import sys
from pathlib import Path

import pytest
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel
from pydantic_ai.toolsets import ApprovalRequiredToolset, PrefixedToolset

from concierge.agent import (
    SYSTEM_PROMPT,
    build_agent,
    build_hamcp_toolset,
    build_skill_toolset,
)
from concierge.config import Settings
from concierge.gating import approval_callback

STUB = str(Path(__file__).parent / "stub_mcp_server.py")


@pytest.fixture(autouse=True)
def _dummy_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Agent() eagerly resolves the default "anthropic:..." model string at
    # construction, and AnthropicProvider requires a key even though every
    # run here overrides the model with TestModel. Deliberate fail-fast:
    # a missing key should crash at startup, not at the first chat turn.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def stub_toolset() -> MCPToolset:
    return MCPToolset(StdioTransport(command=sys.executable, args=[STUB]))


async def test_read_only_tool_runs_without_approval() -> None:
    toolset = stub_toolset().approval_required(approval_callback)
    agent = await build_agent(Settings(), toolsets=[toolset])
    result = await agent.run(
        "What is the temperature in the kitchen?",
        model=TestModel(call_tools=["get_temperature"]),
    )
    # ran to completion: plain text output, no interrupt
    assert isinstance(result.output, str)


async def test_destructive_tool_pauses_then_resumes() -> None:
    toolset = stub_toolset().approval_required(approval_callback)
    agent = await build_agent(Settings(), toolsets=[toolset])
    model = TestModel(call_tools=["delete_everything"])

    result = await agent.run("Delete everything in the basement", model=model)
    assert isinstance(result.output, DeferredToolRequests)
    [call] = result.output.approvals
    assert call.tool_name == "delete_everything"

    results = DeferredToolResults()
    results.approvals[call.tool_call_id] = True
    resumed = await agent.run(
        model=model,
        message_history=result.all_messages(),
        deferred_tool_results=results,
    )
    assert isinstance(resumed.output, str)


async def test_auto_run_tools_skips_gating() -> None:
    settings = Settings(auto_run_tools=True)
    # build_agent must NOT wrap in approval_required when auto_run_tools is on;
    # here we hand it the raw toolset and assert the run completes ungated.
    agent = await build_agent(settings, toolsets=[stub_toolset()])
    result = await agent.run(
        "Delete everything",
        model=TestModel(call_tools=["delete_everything"]),
    )
    assert isinstance(result.output, str)


async def test_system_prompt_carries_discovery_policy() -> None:
    agent = await build_agent(Settings(), toolsets=[stub_toolset()])
    assert isinstance(agent, Agent)
    assert "search" in SYSTEM_PROMPT.lower()


# --- Toolset builder invariants ---------------------------------------------
# Construction-time structure checks: MCPToolset construction never connects,
# so these are cheap and need no live server. They assert against the concrete
# wrapper classes (ApprovalRequiredToolset / PrefixedToolset) and their public
# `wrapped` attribute; acceptable coupling given the hard pydantic-ai-slim
# ==2.8.0 pin in pyproject.toml.


def test_hamcp_toolset_is_gated_and_unprefixed() -> None:
    toolset = build_hamcp_toolset(Settings(ha_url="http://ha:8123", ha_token="t"))
    # Gated (approval wrapper outermost), never prefixed: ha-mcp tools
    # already carry ha_* names.
    assert isinstance(toolset, ApprovalRequiredToolset)
    assert not isinstance(toolset, PrefixedToolset)
    assert toolset.approval_required_func is approval_callback
    inner = toolset.wrapped
    assert isinstance(inner, MCPToolset)
    # The stdio transport must carry the HA connection env for ha-mcp.
    env = inner.client.transport.env
    assert env["HOMEASSISTANT_URL"] == "http://ha:8123"
    assert env["HOMEASSISTANT_TOKEN"] == "t"


def test_hamcp_toolset_ungated_when_auto_run() -> None:
    settings = Settings(auto_run_tools=True, ha_url="http://ha:8123", ha_token="t")
    toolset = build_hamcp_toolset(settings)
    # auto_run_tools bypasses gating entirely: the raw toolset, no wrapper.
    assert type(toolset) is MCPToolset


def test_skill_toolset_prefixed_outermost_gated_inner() -> None:
    toolset = build_skill_toolset("pixoo", "http://skill:9000/mcp", Settings())
    # Prefix outermost, approval wrapping the raw MCPToolset innermost.
    assert isinstance(toolset, PrefixedToolset)
    assert toolset.prefix == "pixoo"
    assert isinstance(toolset.wrapped, ApprovalRequiredToolset)
    assert toolset.wrapped.approval_required_func is approval_callback
    assert isinstance(toolset.wrapped.wrapped, MCPToolset)


def test_skill_toolset_auto_run_prefixes_raw_toolset() -> None:
    settings = Settings(auto_run_tools=True)
    toolset = build_skill_toolset("pixoo", "http://skill:9000/mcp", settings)
    # Still namespaced, but no approval wrapper in between.
    assert isinstance(toolset, PrefixedToolset)
    assert type(toolset.wrapped) is MCPToolset
