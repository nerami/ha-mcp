import socket

from fastapi import FastAPI
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
