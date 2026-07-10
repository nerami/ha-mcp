"""FastAPI app: the AG-UI run endpoint plus the thread REST surface.

POST /agui uses Pydantic AI's AGUIAdapter (manual form: build_run_input ->
run_stream -> encode_stream) with a tee that accumulates the run's events
and persists the whole thread once at stream end. AG-UI is
client-owns-messages, so RunAgentInput.messages is the run's context; the
store exists for cross-session rehydration via GET /threads/{id}.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent
from pydantic_ai.ui.ag_ui import AGUIAdapter

from concierge.config import Settings
from concierge.sessions import SessionStore
from concierge.stream import MessageAccumulator
from concierge.title import generate_title

logger = logging.getLogger(__name__)

TitleFn = Callable[..., Awaitable[str]]


class RenameBody(BaseModel):
    title: str


def _first_user_text(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") == "user" and message.get("content"):
            return str(message["content"])
    return ""


def create_app(
    settings: Settings,
    *,
    agent: Agent,
    store: SessionStore,
    title_fn: TitleFn = generate_title,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        # Hold every toolset (MCP subprocess/connection) open for the app's
        # lifetime. Without this, each POST /agui enters and exits the agent's
        # toolsets independently: MCPToolset ref-counts entry/exit via
        # `_running_count` and tears down at zero, so the bundled ha-mcp
        # stdio subprocess would otherwise be spawned, handshaked, and
        # tools-listed fresh on every single turn. Entering here once keeps
        # `_running_count` >= 1, so the per-run enter/exit inside
        # `adapter.run_stream()` becomes a cheap refcount no-op.
        async with agent:
            yield

    app = FastAPI(title="concierge", lifespan=lifespan)

    async def _maybe_title(thread_id: str, messages: list[dict[str, Any]]) -> None:
        # to_thread here is safe: if cancellation lands in this function the
        # title is merely skipped -- the turn's messages were already durably
        # persisted by the synchronous write in teed()'s finally block.
        if await asyncio.to_thread(store.get_title, thread_id) is not None:
            return
        user_text = _first_user_text(messages)
        if not user_text:
            return
        try:
            title = await title_fn(settings, user_text)
            await asyncio.to_thread(store.set_title, thread_id, title)
        except Exception:  # noqa: BLE001 - titling must never break a turn
            logger.exception("title generation failed for thread %s", thread_id)

    @app.post("/agui")
    async def run_agui(request: Request) -> Response:
        try:
            run_input = AGUIAdapter.build_run_input(await request.body())
        except ValidationError as exc:
            return JSONResponse(
                json.loads(exc.json()),
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        # Pass the raw (possibly absent, possibly "*/*") header through; the
        # event stream resolves the actual wire content type below rather
        # than us assuming the header value doubles as a valid media type.
        adapter = AGUIAdapter(
            agent=agent, run_input=run_input, accept=request.headers.get("accept")
        )
        event_stream = adapter.build_event_stream()

        initial = [
            m.model_dump(by_alias=True, exclude_none=True)
            for m in run_input.messages
        ]
        accumulator = MessageAccumulator(initial)

        run_kwargs: dict[str, Any] = {}
        model_override = getattr(app.state, "model_override", None)
        if model_override is not None:  # test seam; production never sets it
            run_kwargs["model"] = model_override

        async def teed() -> AsyncIterator[Any]:
            try:
                async for event in adapter.run_stream(**run_kwargs):
                    accumulator.feed(event)
                    yield event
            finally:
                # Deliberately synchronous: this write must survive
                # client-disconnect cancellation (an awaited to_thread here
                # would be cancelled mid-unwind and silently drop the turn).
                # WAL SQLite + small threads keep the event-loop block to
                # milliseconds.
                store.replace_messages(run_input.thread_id, accumulator.messages())
                await _maybe_title(run_input.thread_id, accumulator.messages())

        return StreamingResponse(
            event_stream.encode_stream(teed()), media_type=event_stream.content_type
        )

    @app.get("/threads")
    async def list_threads() -> list[dict[str, Any]]:
        return await asyncio.to_thread(store.list_threads)

    @app.get("/threads/{thread_id}")
    async def get_thread(thread_id: str) -> Response:
        messages = await asyncio.to_thread(store.get_messages, thread_id)
        if not messages:
            return JSONResponse({"error": "thread not found"}, status_code=404)
        return JSONResponse(messages)

    @app.patch("/threads/{thread_id}")
    async def rename_thread(thread_id: str, body: RenameBody) -> Response:
        renamed = await asyncio.to_thread(store.rename_thread, thread_id, body.title)
        if not renamed:
            return JSONResponse({"error": "thread not found"}, status_code=404)
        return JSONResponse({"id": thread_id, "title": body.title})

    @app.delete("/threads/{thread_id}")
    async def delete_thread(thread_id: str) -> Response:
        deleted = await asyncio.to_thread(store.delete_thread, thread_id)
        if not deleted:
            return JSONResponse({"error": "thread not found"}, status_code=404)
        return Response(status_code=204)

    return app
