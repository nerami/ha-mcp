#!/usr/bin/env python3
"""Add-on entrypoint: HA options -> CONCIERGE_* env, then launch the backend.

Home Assistant writes the user's add-on options to /data/options.json. This
maps them onto the environment variables `concierge.config.Settings` reads,
supplies the HA connection from the Supervisor token (the same
`http://supervisor/core` + SUPERVISOR_TOKEN the main ha-mcp add-on uses), and
`exec`s `python -m concierge`. No bashio; stdlib only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

OPTIONS_FILE = Path("/data/options.json")
HA_CORE_URL = "http://supervisor/core"


def _log(msg: str) -> None:
    print(f"[run] {msg}", flush=True)


def build_env(options: dict, supervisor_token: str | None) -> dict[str, str]:
    """Pure mapping of add-on options -> CONCIERGE_* env (testable)."""
    env: dict[str, str] = {}

    def opt(env_key: str, value: object) -> None:
        # Only set string options when non-empty so Settings keeps its defaults.
        if isinstance(value, str) and value:
            env[env_key] = value

    opt("CONCIERGE_PROVIDER", options.get("provider"))
    opt("CONCIERGE_MODEL", options.get("model"))
    opt("CONCIERGE_TITLE_MODEL", options.get("title_model"))
    opt("CONCIERGE_API_KEY", options.get("api_key"))
    opt("CONCIERGE_BASE_URL", options.get("base_url"))
    opt("CONCIERGE_LOG_LEVEL", options.get("log_level"))
    env["CONCIERGE_AUTO_RUN_TOOLS"] = "true" if options.get("auto_run_tools") else "false"
    env["CONCIERGE_TRACING"] = "true" if options.get("tracing") else "false"
    env["CONCIERGE_SKILLS"] = json.dumps(options.get("skills") or [])

    # HA connection: Supervisor core proxy + the add-on's own token. ha-mcp
    # (bundled) receives these via the backend's HOMEASSISTANT_URL/TOKEN.
    env["CONCIERGE_HA_URL"] = HA_CORE_URL
    env["CONCIERGE_HA_TOKEN"] = supervisor_token or ""
    return env


def load_options() -> dict:
    """Read /data/options.json, returning {} on any read/parse/shape problem.

    This runs as PID 1 in the add-on container, so a corrupt or hand-edited
    options file must degrade to defaults rather than crash-loop the add-on.
    """
    if not OPTIONS_FILE.is_file():
        return {}
    try:
        options = json.loads(OPTIONS_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        _log(f"could not read {OPTIONS_FILE}: {exc}; using defaults")
        return {}
    if not isinstance(options, dict):
        _log("options.json is not a JSON object; using defaults")
        return {}
    return options


def main() -> None:
    options = load_options()

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        _log(
            "SUPERVISOR_TOKEN not set — bundled ha-mcp requires a non-empty HA "
            "token and will fail to start without it (normal only outside Supervisor)"
        )

    os.environ.update(build_env(options, token))
    _log(f"launching concierge (provider={os.environ.get('CONCIERGE_PROVIDER', 'anthropic')})")
    os.execvp("python3", ["python3", "-m", "concierge"])


if __name__ == "__main__":
    main()
