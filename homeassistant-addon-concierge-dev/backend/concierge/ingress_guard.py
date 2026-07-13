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
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def resolve_supervisor_ips(host: str = "supervisor") -> frozenset[str]:
    """The Supervisor container's IP(s); empty when the host can't resolve."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return frozenset()
    return frozenset(str(info[4][0]) for info in infos)


def install_ingress_guard(app: FastAPI, *, allowed_ips: frozenset[str]) -> None:
    """403 any request whose peer isn't Supervisor. No-op when allowed is empty."""
    if not allowed_ips:
        logger.warning(
            "ingress guard PERMISSIVE — Supervisor not resolvable "
            "(dev/CI/standalone run); not enforcing request source"
        )
    else:
        logger.info("ingress guard active — Supervisor at %s", sorted(allowed_ips))

    @app.middleware("http")
    async def _guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if allowed_ips:
            peer = request.client.host if request.client else None
            if peer not in allowed_ips:
                logger.warning(
                    "ingress guard rejected %s %s from non-Supervisor peer %s",
                    request.method,
                    request.url.path,
                    peer,
                )
                return JSONResponse(
                    {"error": "forbidden: reach this add-on through Home Assistant"},
                    status_code=403,
                )
        return await call_next(request)
