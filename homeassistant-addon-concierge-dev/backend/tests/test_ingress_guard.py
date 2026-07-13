import asyncio
import socket
from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from concierge import ingress_guard


def _app(allowed: frozenset[str]) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    ingress_guard.install_ingress_guard(app, allowed_ips=allowed)
    return app


def test_permissive_when_no_supervisor_resolved() -> None:
    # Empty allow-set = dev/CI/docker-run: everything passes.
    with TestClient(_app(frozenset())) as c:
        assert c.get("/ping").status_code == 200


def test_rejects_peer_not_in_allowset() -> None:
    # TestClient's peer host is "testclient"; an allow-set without it => 403.
    with TestClient(_app(frozenset({"172.30.32.2"}))) as c:
        resp = c.get("/ping")
        assert resp.status_code == 403


def test_allows_peer_in_allowset() -> None:
    with TestClient(_app(frozenset({"testclient"}))) as c:
        assert c.get("/ping").status_code == 200


def test_resolve_supervisor_ips_empty_on_unknown_host(monkeypatch) -> None:
    def boom(*a: object, **k: object) -> object:
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    assert ingress_guard.resolve_supervisor_ips() == frozenset()


def test_resolve_supervisor_ips_collects_addresses(monkeypatch) -> None:
    def fake(host, *a, **k):  # type: ignore[no-untyped-def]
        assert host == "supervisor"
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.32.2", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.32.2", 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert ingress_guard.resolve_supervisor_ips() == frozenset({"172.30.32.2"})


async def test_websocket_rejected_sends_close_for_non_allowed_peer() -> None:
    # Drives the guard directly with a hand-built websocket scope: proves a
    # rejected websocket peer gets an ASGI websocket.close, not an HTTP
    # JSONResponse (which would be invalid on a websocket scope).
    async def inner_app(scope, receive, send):  # type: ignore[no-untyped-def]
        raise AssertionError("inner app must not be invoked for a rejected peer")

    guard = ingress_guard._IngressGuard(inner_app, allowed_ips=frozenset({"172.30.32.2"}))

    sent: list[dict] = []

    async def send(message: dict) -> None:  # type: ignore[no-untyped-def]
        sent.append(message)

    async def receive() -> dict:  # type: ignore[no-untyped-def]
        raise AssertionError("receive should not be consumed by the guard")

    scope = {"type": "websocket", "client": ("10.0.0.5", 12345), "path": "/ws"}
    await guard(scope, receive, send)

    assert sent == [{"type": "websocket.close", "code": 1008}]


async def test_websocket_allowed_peer_passes_through() -> None:
    # Same hand-built-scope style as above, but for an allowed peer: the guard
    # must delegate to the wrapped app untouched (no close, no response sent).
    calls: list[dict] = []

    async def inner_app(scope, receive, send):  # type: ignore[no-untyped-def]
        calls.append(scope)

    guard = ingress_guard._IngressGuard(inner_app, allowed_ips=frozenset({"172.30.32.2"}))

    async def send(message: dict) -> None:  # type: ignore[no-untyped-def]
        raise AssertionError("guard must not send anything for an allowed peer")

    async def receive() -> dict:  # type: ignore[no-untyped-def]
        raise AssertionError("guard must not consume receive for an allowed peer")

    scope = {"type": "websocket", "client": ("172.30.32.2", 12345), "path": "/ws"}
    await guard(scope, receive, send)

    assert calls == [scope]


async def test_streaming_response_passes_through_unbuffered() -> None:
    # Proves the pure-ASGI guard delegates the stream instead of collecting it:
    # chunks arrive one at a time, in order, through the guarded app.
    chunks = [b"chunk-0\n", b"chunk-1\n", b"chunk-2\n"]

    app = FastAPI()

    @app.get("/stream")
    def stream() -> StreamingResponse:
        async def gen() -> AsyncIterator[bytes]:
            for c in chunks:
                yield c
                await asyncio.sleep(0)  # yield control between chunks

        return StreamingResponse(gen(), media_type="text/plain")

    # Permissive (empty allow-set): the passthrough path we want to exercise.
    ingress_guard.install_ingress_guard(app, allowed_ips=frozenset())

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        received: list[bytes] = []
        async with client.stream("GET", "/stream") as resp:
            assert resp.status_code == 200
            async for part in resp.aiter_bytes():
                if part:
                    received.append(part)

    assert b"".join(received) == b"".join(chunks)
