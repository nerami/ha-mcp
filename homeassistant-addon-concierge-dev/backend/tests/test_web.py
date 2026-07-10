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
    # this file overrides the model with TestModel. Deliberate fail-fast: a
    # missing key should crash at startup, not at the first chat turn. Mirrors
    # the identical fixture in test_agent.py.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


def run_input(thread_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "runId": str(uuid.uuid4()),
        "messages": messages,
        "tools": [],
        "context": [],
        "state": None,
        "forwardedProps": None,
    }


def sse_events(body: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


@pytest.fixture
async def client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    toolset = MCPToolset(
        StdioTransport(command=sys.executable, args=[STUB])
    ).approval_required(approval_callback)
    agent = await build_agent(settings, toolsets=[toolset])
    store = SessionStore(tmp_path / "concierge.db")

    async def fake_title(settings: Settings, user_text: str, **kwargs: Any) -> str:
        return "Test title"

    app = create_app(settings, agent=agent, store=store, title_fn=fake_title)
    # TestModel: answer directly without calling tools.
    app.state.model_override = TestModel(call_tools=[])
    with TestClient(app) as c:
        yield c, store


async def test_agui_run_streams_and_persists(client) -> None:
    c, store = client
    tid = "t-" + uuid.uuid4().hex[:8]
    user = {"id": "u1", "role": "user", "content": "hello"}
    resp = c.post("/agui", json=run_input(tid, [user]))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    types = [e["type"] for e in sse_events(resp.text)]
    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_FINISHED"

    # persisted: user message + at least one assistant message
    stored = store.get_messages(tid)
    assert stored[0] == user
    assert any(m.get("role") == "assistant" for m in stored)
    # title generated for the new thread
    assert store.get_title(tid) == "Test title"


async def test_agui_invalid_input_returns_422(client) -> None:
    c, _store = client
    resp = c.post(
        "/agui",
        content=b'{"not": "a run input"}',
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 422


async def test_thread_crud(client) -> None:
    c, store = client
    store.replace_messages("t9", [{"id": "u1", "role": "user", "content": "x"}])

    listed = c.get("/threads").json()
    assert [t["id"] for t in listed] == ["t9"]

    assert c.get("/threads/t9").json() == [
        {"id": "u1", "role": "user", "content": "x"}
    ]
    assert c.get("/threads/missing").status_code == 404

    assert c.patch("/threads/t9", json={"title": "Renamed"}).status_code == 200
    assert store.get_title("t9") == "Renamed"
    assert c.patch("/threads/no", json={"title": "x"}).status_code == 404

    assert c.delete("/threads/t9").status_code == 204
    assert c.delete("/threads/t9").status_code == 404
