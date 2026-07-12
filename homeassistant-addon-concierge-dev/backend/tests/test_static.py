import asyncio
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from concierge.config import Settings
from concierge.sessions import SessionStore
from concierge.web import create_app


def make_app(tmp_path: Path, static_dir: Path | None):
    settings = Settings(data_dir=tmp_path, static_dir=static_dir)

    class _NoAgent:  # static routes never touch the agent
        async def __aenter__(self) -> "_NoAgent":
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    store = SessionStore(tmp_path / "db.sqlite")
    return create_app(settings, agent=_NoAgent(), store=store)  # type: ignore[arg-type]


def write_site(tmp_path: Path) -> Path:
    site = tmp_path / "dist"
    site.mkdir()
    (site / "index.html").write_text("<html>app</html>")
    (site / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    return site


def test_serves_real_files_and_spa_fallback(tmp_path: Path) -> None:
    site = write_site(tmp_path)
    with TestClient(make_app(tmp_path, site)) as c:
        assert c.get("/app.js").text == "console.log(1)"
        assert "app" in c.get("/").text
        assert "app" in c.get("/some/spa/route").text  # fallback


def test_path_traversal_is_blocked(tmp_path: Path) -> None:
    site = write_site(tmp_path)
    with TestClient(make_app(tmp_path, site)) as c:
        resp = c.get("/%2e%2e/secret.txt")
        assert "nope" not in resp.text


def test_api_routes_not_shadowed(tmp_path: Path) -> None:
    site = write_site(tmp_path)
    with TestClient(make_app(tmp_path, site)) as c:
        assert c.get("/threads").json() == []


def test_no_static_dir_means_no_route(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path, None)) as c:
        assert c.get("/anything").status_code == 404


def test_static_dir_without_index_disables_static_serving(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A broken/incomplete build (no index.html) must not 500 every request.

    The catch-all route is simply not registered: static paths 404, the API
    keeps working, and a warning points at the incomplete build.
    """
    site = tmp_path / "dist"
    site.mkdir()
    (site / "app.js").write_text("console.log(1)")  # real file, but no index.html

    with caplog.at_level(logging.WARNING, logger="concierge.web"):
        app = make_app(tmp_path, site)

    assert "no index.html" in caplog.text
    with TestClient(app) as c:
        assert c.get("/").status_code == 404
        assert c.get("/anything").status_code == 404
        assert c.get("/threads").json() == []


def test_traversal_check_itself_blocks_escaping_path(tmp_path: Path) -> None:
    """Exercise the handler directly with a literal "../" full_path.

    TestClient's HTTP-level request (`/%2e%2e/secret.txt` above) may get
    normalized by the ASGI stack before the handler runs, which would let
    a broken safety check pass that test by accident. Calling the route
    function directly proves the `is_relative_to(root)` guard -- not request
    normalization -- is what keeps the resolved candidate inside the static
    root.
    """
    site = write_site(tmp_path)
    app = make_app(tmp_path, site)
    (spa_route,) = [r for r in app.routes if getattr(r, "path", None) == "/{full_path:path}"]

    response = asyncio.run(spa_route.endpoint("../secret.txt"))

    # Falls back to index.html -- never the escaped secret.txt.
    assert Path(response.path) == (site / "index.html").resolve()
