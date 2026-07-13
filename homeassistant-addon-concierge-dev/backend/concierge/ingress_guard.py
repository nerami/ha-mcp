"""Reject requests that did not arrive through Supervisor's ingress proxy.

The add-on publishes no host port and binds only the ingress port, but on the
shared `hassio` docker network any co-resident add-on can still reach that port
directly and drive the unauthenticated `/agui` (including approving destructive
tools). Legitimate traffic always arrives via Supervisor, which proxies the
final hop — so its real TCP peer is the Supervisor container. A co-resident
add-on connecting directly presents its own peer IP and cannot spoof it at the
socket layer (unlike an `X-Ingress-Path` header, which it could forge).

The guard resolves Supervisor's IP(s) at startup. If it can't (no `supervisor`
DNS name — i.e. a dev box, CI, or a plain `docker run`), it stays PERMISSIVE:
there is no ingress to enforce there, and a false rejection would brick the UI.

It is a pure ASGI middleware (not `@app.middleware("http")` /
`BaseHTTPMiddleware`): on the allowed/permissive path it invokes the wrapped app
directly with the original `scope`/`receive`/`send`, so it never wraps or
buffers the response body and never intercepts client-disconnect signalling.
That matters for the SSE `/agui` endpoint, whose durability guarantee relies on
a mid-stream disconnect propagating into the run's `finally`; `BaseHTTPMiddleware`
is known to buffer `StreamingResponse` and break that, so it is avoided here.
"""

from __future__ import annotations

import logging
import socket

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


def resolve_supervisor_ips(host: str = "supervisor") -> frozenset[str]:
    """The Supervisor container's IP(s); empty when the host can't resolve."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return frozenset()
    return frozenset(str(info[4][0]) for info in infos)


class _IngressGuard:
    """Pure ASGI middleware: 403 non-Supervisor peers, else delegate untouched."""

    def __init__(self, app: ASGIApp, allowed_ips: frozenset[str]) -> None:
        self.app = app
        self.allowed_ips = allowed_ips

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Gate both HTTP and websocket (both carry a real scope["client"] peer);
        # pass lifespan straight through untouched — it has no peer and must pass.
        if scope["type"] in ("http", "websocket") and self.allowed_ips:
            client = scope.get("client")
            peer = client[0] if client else None
            if peer not in self.allowed_ips:
                logger.warning(
                    "ingress guard rejected %s %s from non-Supervisor peer %s",
                    scope.get("method"),
                    scope.get("path"),
                    peer,
                )
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await JSONResponse(
                        {"error": "forbidden: reach this add-on through Home Assistant"},
                        status_code=403,
                    )(scope, receive, send)
                return
        # Allowed (or permissive): call the wrapped app directly — zero
        # interference with StreamingResponse bodies or disconnect signalling.
        await self.app(scope, receive, send)


def install_ingress_guard(app: FastAPI, *, allowed_ips: frozenset[str]) -> None:
    """Install the guard. Enforcement is a no-op when allowed_ips is empty."""
    if not allowed_ips:
        logger.warning(
            "ingress guard PERMISSIVE — Supervisor not resolvable "
            "(dev/CI/standalone run); not enforcing request source"
        )
    else:
        logger.info("ingress guard active — Supervisor at %s", sorted(allowed_ips))
    app.add_middleware(_IngressGuard, allowed_ips=allowed_ips)
