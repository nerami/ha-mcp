import sys
from pathlib import Path

from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel

from concierge.agent import SYSTEM_PROMPT, build_agent
from concierge.config import Settings
from concierge.gating import approval_callback

STUB = str(Path(__file__).parent / "stub_mcp_server.py")


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
