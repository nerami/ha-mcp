import importlib.util
from pathlib import Path

ADDON_DIR = Path(__file__).resolve().parents[2]


def _load_run():
    spec = importlib.util.spec_from_file_location("addon_run", ADDON_DIR / "run.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_maps_options_to_concierge_env() -> None:
    run = _load_run()
    env = run.build_env(
        {
            "provider": "openai",
            "model": "gpt-5",
            "title_model": "",
            "api_key": "sk-x",
            "base_url": "",
            "auto_run_tools": True,
            "skills": ["pixoo", "http://x:9000/mcp"],
            "tracing": False,
            "log_level": "debug",
        },
        supervisor_token="tok-123",
    )
    assert env["CONCIERGE_PROVIDER"] == "openai"
    assert env["CONCIERGE_MODEL"] == "gpt-5"
    assert env["CONCIERGE_API_KEY"] == "sk-x"
    assert env["CONCIERGE_AUTO_RUN_TOOLS"] == "true"
    assert env["CONCIERGE_SKILLS"] == '["pixoo", "http://x:9000/mcp"]'
    assert env["CONCIERGE_TRACING"] == "false"
    assert env["CONCIERGE_LOG_LEVEL"] == "debug"
    # HA connection from the Supervisor token
    assert env["CONCIERGE_HA_URL"] == "http://supervisor/core"
    assert env["CONCIERGE_HA_TOKEN"] == "tok-123"


def test_blank_optionals_are_omitted() -> None:
    run = _load_run()
    env = run.build_env(
        {"provider": "anthropic", "model": "claude", "title_model": "",
         "api_key": "", "base_url": "", "auto_run_tools": False, "skills": [],
         "tracing": False, "log_level": "info"},
        supervisor_token=None,
    )
    assert "CONCIERGE_TITLE_MODEL" not in env
    assert "CONCIERGE_API_KEY" not in env
    assert "CONCIERGE_BASE_URL" not in env
    assert env["CONCIERGE_SKILLS"] == "[]"
    # No supervisor token -> empty HA token (warn, don't crash)
    assert env["CONCIERGE_HA_TOKEN"] == ""
    assert env["CONCIERGE_HA_URL"] == "http://supervisor/core"


def test_missing_options_file_yields_defaults() -> None:
    run = _load_run()
    env = run.build_env({}, supervisor_token="t")
    # empty options -> only the always-set keys, no crash
    assert env["CONCIERGE_SKILLS"] == "[]"
    assert env["CONCIERGE_AUTO_RUN_TOOLS"] == "false"


def test_load_options_non_dict_falls_back_to_empty(tmp_path, monkeypatch) -> None:
    run = _load_run()
    options_file = tmp_path / "options.json"
    options_file.write_text("[]")
    monkeypatch.setattr(run, "OPTIONS_FILE", options_file)
    # Valid JSON but not an object -> defaults, no crash.
    assert run.load_options() == {}


def test_load_options_malformed_falls_back_to_empty(tmp_path, monkeypatch) -> None:
    run = _load_run()
    options_file = tmp_path / "options.json"
    options_file.write_text("{not valid json")
    monkeypatch.setattr(run, "OPTIONS_FILE", options_file)
    assert run.load_options() == {}


def test_load_options_reads_object(tmp_path, monkeypatch) -> None:
    run = _load_run()
    options_file = tmp_path / "options.json"
    options_file.write_text('{"provider": "openai"}')
    monkeypatch.setattr(run, "OPTIONS_FILE", options_file)
    assert run.load_options() == {"provider": "openai"}
