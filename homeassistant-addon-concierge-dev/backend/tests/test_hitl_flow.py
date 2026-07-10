"""HITL over the wire: destructive tool call interrupts, client resumes.

Proves the §5.5 human-in-the-loop flow end-to-end through the AG-UI HTTP
endpoint: turn 1 gates `delete_everything` (destructiveHint) and ends the
run with a `RUN_FINISHED` interrupt outcome; turn 2 resumes the same thread
with an approval and the tool actually executes.

Field names below come from the installed `ag_ui.core` models, not the
task brief's provisional guess -- discovered via:

    RunAgentInput.model_fields.keys()
        -> includes "resume" (list[ResumeEntry] | None, alias "resume")
    ResumeEntry.model_fields
        -> interrupt_id (alias "interruptId", required)
        -> status: Literal["resolved", "cancelled"] (required)
        -> payload: Any | None
    RunFinishedEvent.outcome -> RunFinishedInterruptOutcome | RunFinishedSuccessOutcome
    RunFinishedInterruptOutcome.model_fields
        -> type: Literal["interrupt"]
        -> interrupts: list[Interrupt]
    Interrupt.model_fields -> id, reason, message, tool_call_id (alias
        "toolCallId"), response_schema, expires_at, metadata

`pydantic_ai.ui.ag_ui._interrupt.resume_entry_to_approval` requires
`status` on every `ResumeEntry` (there's no default) and only treats
`payload.approved is True` as an approval -- anything else denies. So the
brief's `{"id": ..., "payload": {"approved": True}}` needed two fixes:
`id` -> `interruptId`, and an explicit `"status": "resolved"` added.
"""

import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel

from concierge.agent import build_agent
from concierge.config import Settings
from concierge.gating import approval_callback
from concierge.sessions import SessionStore
from concierge.web import create_app

STUB = str(Path(__file__).parent / "stub_mcp_server.py")


@pytest.fixture(autouse=True)
def _dummy_anthropic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Agent() eagerly resolves the default "anthropic:..." model string at
    # construction (via build_agent -> build_model), even though every run in
    # this file overrides the model with TestModel. Mirrors test_web.py.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def sse_events(body: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def base_input(thread_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "runId": str(uuid.uuid4()),
        "messages": messages,
        "tools": [],
        "context": [],
        "state": None,
        "forwardedProps": None,
    }


@pytest.fixture
async def client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    toolset = MCPToolset(
        StdioTransport(command=sys.executable, args=[STUB])
    ).approval_required(approval_callback)
    agent = await build_agent(settings, toolsets=[toolset])
    store = SessionStore(tmp_path / "concierge.db")

    async def fake_title(settings: Settings, user_text: str, **kw: Any) -> str:
        return "t"

    app = create_app(settings, agent=agent, store=store, title_fn=fake_title)
    app.state.model_override = TestModel(call_tools=["delete_everything"])
    with TestClient(app) as c:
        yield c, store


async def test_destructive_tool_interrupts_then_resumes(client) -> None:
    c, store = client
    tid = "t-" + uuid.uuid4().hex[:8]
    user = {"id": "u1", "role": "user", "content": "delete everything downstairs"}

    # Turn 1: gated tool -> RUN_FINISHED carries an interrupt outcome.
    first = c.post("/agui", json=base_input(tid, [user]))
    assert first.status_code == 200
    events = sse_events(first.text)
    finished = [e for e in events if e["type"] == "RUN_FINISHED"][-1]
    outcome = finished.get("outcome") or {}
    assert outcome.get("type") == "interrupt", f"expected interrupt outcome, got: {events}"
    interrupts = outcome["interrupts"]
    assert len(interrupts) == 1
    # No TOOL_CALL_RESULT on turn 1: the destructive call is gated, not run.
    assert "TOOL_CALL_RESULT" not in [e["type"] for e in events]

    # Turn 2: resume with approval; stream must contain the tool result.
    stored = store.get_messages(tid)
    resume_input = base_input(tid, stored)
    resume_input["resume"] = [
        {
            "interruptId": interrupts[0]["id"],
            "status": "resolved",
            "payload": {"approved": True},
        }
    ]
    second = c.post("/agui", json=resume_input)
    assert second.status_code == 200
    second_events = sse_events(second.text)
    types = [e["type"] for e in second_events]
    assert "TOOL_CALL_RESULT" in types, f"expected tool result, got: {second_events}"
    final = [e for e in second_events if e["type"] == "RUN_FINISHED"][-1]
    assert (final.get("outcome") or {}).get("type") != "interrupt"
