from concierge.__main__ import make_production_app


async def test_make_production_app_builds(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CONCIERGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONCIERGE_HA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("CONCIERGE_HA_TOKEN", "fake")
    monkeypatch.setenv("CONCIERGE_API_KEY", "dummy")
    app = await make_production_app()
    routes = {r.path for r in app.routes}
    assert {"/agui", "/threads", "/threads/{thread_id}"} <= routes
