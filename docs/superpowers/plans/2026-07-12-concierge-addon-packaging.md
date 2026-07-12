# Concierge Add-on Packaging Implementation Plan (Plan 3 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the completed Concierge backend + frontend as an installable Home Assistant **dev-channel add-on** — a `config.yaml` manifest, an options→env launcher, and a multi-stage Dockerfile that Supervisor builds locally — proven by a real `docker build` and a `docker run` smoke that serves the built UI and API.

**Architecture:** Supervisor builds the add-on locally from the Dockerfile (the Webhook Proxy pattern — no prebuilt ghcr image, no `build.yaml`; a "release" is a `version` bump in `config.yaml`). The Dockerfile is multi-stage: a Node stage builds the Lit frontend, a `uv` stage builds the Python venv (backend + bundled ha-mcp), and a slim runtime stage copies both. HA options land in `/data/options.json`; a stdlib `run.py` maps them to `CONCIERGE_*` env (and fills the HA connection from the Supervisor token) before `exec`-ing `python -m concierge`. UI is served over **ingress** (`ingress_stream: true` for SSE); no host port is mapped.

**Tech Stack:** HA add-on `config.yaml` · multi-stage Docker (`node:22-slim` → `ghcr.io/astral-sh/uv:…python3.13` → `python:3.13-slim`) · stdlib `run.py` · pytest (backend uv env) for config/parity tests.

**Scope:** This plan delivers the installable **dev flavor only** (`homeassistant-addon-concierge-dev/`). The dev-first/promote release automation (promote sync script + version-guard/stable-guard/promote/dev-bump workflows, mirroring `homeassistant-addon-webhook-proxy*`) is deferred to **Plan 4**; the stable flavor dir does not exist until its first promote. Backend (Plan 1) and frontend (Plan 2) are complete and unchanged by this plan.

**Authorities:** `docs/superpowers/notes/2026-07-10-backend-handoff.md` (§"Plan 2 handoff" — build gate, ingress/SSE, security). `homeassistant-addon-webhook-proxy/AGENTS.md` (dev-first pattern). `homeassistant-addon/Dockerfile` + `homeassistant-addon/start.py` (uv-build + Supervisor HA-env patterns). Spec §7-8.

## Global Constraints

- **Add-on dir:** `homeassistant-addon-concierge-dev/` (dev flavor; slug `ha_mcp_concierge_dev`). The existing `backend/` and `frontend/` subdirs are the Plan-1/Plan-2 code — do not modify them; add sibling files (`config.yaml`, `Dockerfile`, `run.py`, `.dockerignore`, docs, `translations/`).
- **Security invariants (non-negotiable — the security note binds them):** `ingress: true`; **no `ports:` key**; **no `host_network: true`**. `/agui` is unauthenticated by design; ingress is the auth boundary. Publishing a port would expose it on the LAN.
- **SSE:** `ingress_stream: true` (Supervisor must not buffer the AG-UI event stream; the response also legitimately stays open past `RUN_FINISHED` for titling).
- **Version:** `config.yaml` `version` is the single release identifier, format `X.Y.Z.devN` (dev channel; Plan 4's guard will enforce the `.devN` suffix). Start at `0.1.0.dev1`. `backend/pyproject.toml` and `frontend/package.json` stay static `"0.0.0"` (repo convention — don't touch).
- **Options ⇔ Settings parity:** every `config.yaml` schema key must map to a `concierge.config.Settings` field of a compatible type; the parity test (Task 3) is the enforcement. Options are the *operator-facing subset* of Settings — `ha_url`/`ha_token`/`data_dir`/`host`/`port` are NOT options (Supervisor/fixed).
- **HA connection:** ha-mcp reaches HA exactly as the main add-on does — `HOMEASSISTANT_URL=http://supervisor/core`, `HOMEASSISTANT_TOKEN=$SUPERVISOR_TOKEN` (verified in `homeassistant-addon/start.py:563,698`). `run.py` sets `CONCIERGE_HA_URL`/`CONCIERGE_HA_TOKEN`, which the backend already forwards to the ha-mcp subprocess. Unlike the main add-on, a missing `SUPERVISOR_TOKEN` must **warn, not hard-exit** (tools/list works without it; keeps the local smoke and degraded modes alive).
- **Base-image pins:** reuse the exact digests the main add-on already pins — runtime `python:3.13-slim@sha256:3de9a8d7aedbb7984dc18f2dff178a7850f16c1ae7c34ba9d7ecc23d0755e35f`, uv builder `ghcr.io/astral-sh/uv:0.11.27-python3.13-trixie-slim@sha256:68bbb9d4281aa16c9780820ceaf4c558d78fb65ce45d42eb589d7234e3f26e15`. Node: `node:22-slim`.
- **Build context** is the add-on dir; Dockerfile paths are relative to it (`backend/`, `frontend/`, `run.py`).
- Commits on `feat/concierge-addon`, never master. Conventional commits (`feat(concierge): …`, addon scope `feat(addon): …` is also fine). Config/parity tests run from `homeassistant-addon-concierge-dev/backend/` via `uv run pytest`; Docker steps from the add-on dir.

---

### Task 1: Add-on manifest, translations, and docs

**Files:**
- Create: `homeassistant-addon-concierge-dev/config.yaml`
- Create: `homeassistant-addon-concierge-dev/translations/en.yaml`
- Create: `homeassistant-addon-concierge-dev/AGENTS.md`
- Create: `homeassistant-addon-concierge-dev/CLAUDE.md` (symlink → `AGENTS.md`)
- Create: `homeassistant-addon-concierge-dev/DOCS.md`
- Create: `homeassistant-addon-concierge-dev/CHANGELOG.md`
- Test: `homeassistant-addon-concierge-dev/backend/tests/test_addon_manifest.py`

**Interfaces:**
- Produces: a valid HA add-on `config.yaml` with the operator option set and the security invariants; the manifest test that pins them.

- [ ] **Step 1: Write `config.yaml`**

```yaml
name: "Concierge for HA MCP (Dev)"
description: "DEV CHANNEL (unstable) — a self-hosted chat concierge for your smart home, powered by ha-mcp. Open it from the Home Assistant app; no external agent needed."
version: "0.1.0.dev1"
slug: "ha_mcp_concierge_dev"
url: "https://github.com/homeassistant-ai/ha-mcp"
stage: experimental
arch:
  - aarch64
  - amd64
init: false
startup: application
boot: manual
# Ingress: the UI is reached only through Supervisor's authenticated proxy.
# ingress_stream keeps the AG-UI SSE event stream unbuffered.
# NO ports: / NO host_network: — /agui is unauthenticated by design and must
# never be exposed on the LAN; ingress is the auth boundary.
ingress: true
ingress_port: 8098
ingress_stream: true
panel_icon: mdi:robot-happy
panel_title: "Concierge (Dev)"
# The add-on talks to HA via the Supervisor core proxy using its own token.
homeassistant_api: true
hassio_api: true
options:
  provider: "anthropic"
  model: "claude-sonnet-5"
  title_model: ""
  api_key: ""
  base_url: ""
  auto_run_tools: false
  skills: []
  tracing: false
  log_level: "info"
schema:
  provider: str
  model: str
  title_model: str?
  api_key: password?
  base_url: str?
  auto_run_tools: bool
  skills:
    - str
  tracing: bool?
  log_level: list(debug|info|warning|error)?
```

(Pin the real default `model`/`title_model` IDs at implementation — Plan 1 used `claude-sonnet-5` / `claude-haiku-4-5`; confirm current IDs. `title_model: ""` means "fall back to the provider default", handled by `Settings.effective_title_model`.)

- [ ] **Step 2: Write `translations/en.yaml`** (option labels shown in the HA UI)

```yaml
---
configuration:
  provider:
    name: LLM provider
    description: >
      Which model provider to use: anthropic (default), openai, google, groq,
      mistral, bedrock, or a custom OpenAI-compatible endpoint (set Base URL).
  model:
    name: Chat model
    description: >
      Model id for the main conversation (e.g. claude-sonnet-5). Assumes a
      high-quality, tool-capable model.
  title_model:
    name: Title model (optional)
    description: >
      Cheaper model used only to name new conversations. Blank = a sensible
      default for your provider.
  api_key:
    name: API key
    description: >
      Credential for the selected provider. Not needed for providers that
      authenticate another way (e.g. AWS Bedrock).
  base_url:
    name: Base URL (optional)
    description: >
      For OpenAI-compatible / local endpoints (Ollama, vLLM, OpenRouter…).
      Leave blank for native providers.
  auto_run_tools:
    name: Auto-run all tools
    description: >
      When on, the concierge runs every tool without asking. Off (default)
      requires your approval before any destructive action.
  skills:
    name: Skill add-ons
    description: >
      Short slugs of installed ha-concierge-skill-* add-ons to mount as extra
      tools (or full http(s)://…/mcp URLs). One per line.
  tracing:
    name: Enable tracing
    description: >
      Export OpenTelemetry traces (point OTEL_EXPORTER_OTLP_* at Langfuse or
      Logfire). Off by default.
  log_level:
    name: Log level
    description: Verbosity of the add-on log (debug, info, warning, error).
```

- [ ] **Step 3: Write `AGENTS.md`** and the `CLAUDE.md` symlink

`AGENTS.md`:

```markdown
# Concierge Add-on (dev flavor)

## What it is
A self-contained Home Assistant add-on: a Lit chat UI (served over Supervisor
ingress) backed by a Pydantic AI agent whose tools are **bundled ha-mcp**
(run in-container over stdio) plus optional `ha-concierge-skill-*` add-ons
discovered over the Supervisor DNS network. It installs nothing into HA Core.

## Layout
- `config.yaml` — add-on manifest (ingress, options).
- `Dockerfile` — multi-stage: Node builds the frontend, `uv` builds the Python
  venv (backend + ha-mcp), slim runtime serves it.
- `run.py` — maps `/data/options.json` → `CONCIERGE_*` env, fills the HA
  connection from `SUPERVISOR_TOKEN`, then `exec`s `python -m concierge`.
- `backend/` — the Pydantic AI service (own uv project; Plan 1).
- `frontend/` — the Lit SPA (own npm project; Plan 2). Built into the image.

## Security invariants (do not weaken)
`/agui` has no authentication — ingress is the auth boundary. The manifest
therefore has **no `ports:` and no `host_network:`**; the UI is reachable only
through Supervisor's ingress proxy. `homeassistant-addon-concierge-dev/backend/tests/test_addon_manifest.py`
fails if any of these invariants regress.

## Options ⇔ Settings
`config.yaml` options are the operator-facing subset of `concierge.config.Settings`
(`ha_url`/`ha_token`/`data_dir`/`host`/`port` are supplied by the runtime, not
options). `test_addon_config_parity.py` enforces that every option maps to a
real Settings field.

## Versioning & flavors
`config.yaml` `version` (format `X.Y.Z.devN`) is the single release id; bump it
on every change. Only the **dev** flavor exists today. The **stable** flavor
(`homeassistant-addon-concierge/`, slug `ha_mcp_concierge`) and the
dev-first/promote automation land in **Plan 4** (mirroring the Webhook Proxy
add-on). Because Concierge installs no custom component, the dev↔stable
transform is config-identity only — the `backend/`/`frontend/` code is byte
-identical across flavors (no token rename).
```

Then: `ln -s AGENTS.md homeassistant-addon-concierge-dev/CLAUDE.md`

- [ ] **Step 4: Write `DOCS.md` and `CHANGELOG.md`** (concise — user-facing add-on page)

`DOCS.md`: a short install/usage doc — what it is (self-hosted concierge chat over your home), how to configure (pick a provider + paste an API key, optional skills), that it's reachable from the HA app, the approval model (destructive actions need your OK unless "Auto-run all tools" is on), and a note that it's a dev-channel/experimental build. Keep under ~80 lines.

`CHANGELOG.md`:

```markdown
# Changelog

## 0.1.0.dev1

- Initial dev-channel release: self-hosted chat concierge over ha-mcp, served
  through Home Assistant ingress. Streaming chat, tool-call rendering,
  human-in-the-loop approval for destructive actions, multi-thread history,
  and skill-add-on extensibility.
```

- [ ] **Step 5: Write the failing manifest test**

`homeassistant-addon-concierge-dev/backend/tests/test_addon_manifest.py`:

```python
"""The add-on manifest (config.yaml) is one dir up from this backend project."""

from pathlib import Path

import pytest
import yaml

ADDON_DIR = Path(__file__).resolve().parents[2]
CONFIG = ADDON_DIR / "config.yaml"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return yaml.safe_load(CONFIG.read_text())


def test_config_is_valid_yaml_with_required_keys(manifest: dict) -> None:
    for key in ("name", "slug", "version", "arch", "options", "schema"):
        assert key in manifest, f"missing required key: {key}"
    assert manifest["slug"] == "ha_mcp_concierge_dev"
    assert set(manifest["arch"]) == {"aarch64", "amd64"}


def test_security_invariants(manifest: dict) -> None:
    # /agui is unauthenticated; ingress is the only allowed exposure.
    assert manifest.get("ingress") is True
    assert manifest.get("ingress_stream") is True, "SSE needs unbuffered ingress"
    assert "ports" not in manifest, "no host port may be published"
    assert manifest.get("host_network") is not True, "host_network would expose /agui"
    assert manifest.get("ingress_port") == 8098


def test_dev_version_is_devN(manifest: dict) -> None:
    import re

    assert re.match(r"^\d+\.\d+\.\d+\.dev\d+$", str(manifest["version"])), (
        "dev add-on version must be X.Y.Z.devN"
    )


def test_options_have_schema_and_vice_versa(manifest: dict) -> None:
    assert set(manifest["options"]) == set(manifest["schema"]), (
        "every option needs a schema entry and vice versa"
    )
```

- [ ] **Step 6: Add `pyyaml` to the backend dev deps, run the test**

In `homeassistant-addon-concierge-dev/backend/pyproject.toml`, add `"pyyaml>=6"` to `[dependency-groups] dev`. Then:

Run: `cd homeassistant-addon-concierge-dev/backend && uv sync && uv run pytest tests/test_addon_manifest.py -v`
Expected: 4 PASS. (If RED first because `config.yaml` doesn't exist yet, that confirms the ordering — write config.yaml, then GREEN.)

- [ ] **Step 7: Commit**

```bash
cd ../..   # worktree root
git add homeassistant-addon-concierge-dev/config.yaml homeassistant-addon-concierge-dev/translations \
  homeassistant-addon-concierge-dev/AGENTS.md homeassistant-addon-concierge-dev/CLAUDE.md \
  homeassistant-addon-concierge-dev/DOCS.md homeassistant-addon-concierge-dev/CHANGELOG.md \
  homeassistant-addon-concierge-dev/backend/pyproject.toml homeassistant-addon-concierge-dev/backend/uv.lock \
  homeassistant-addon-concierge-dev/backend/tests/test_addon_manifest.py
git commit -m "feat(addon): concierge dev-channel manifest, translations, and docs"
```

---

### Task 2: `run.py` — options → env launcher

**Files:**
- Create: `homeassistant-addon-concierge-dev/run.py`
- Test: `homeassistant-addon-concierge-dev/backend/tests/test_run_launcher.py`

**Interfaces:**
- Produces: `run.py` with `build_env(options: dict, supervisor_token: str | None) -> dict[str, str]` (pure, testable — maps HA options to `CONCIERGE_*`) and a `main()` that reads `/data/options.json`, applies the env, and `os.execvp`s `python3 -m concierge`. Bundled ha-mcp gets HA creds via `CONCIERGE_HA_URL`/`CONCIERGE_HA_TOKEN` (the backend forwards them to `HOMEASSISTANT_URL`/`HOMEASSISTANT_TOKEN`).

- [ ] **Step 1: Write the failing test**

`homeassistant-addon-concierge-dev/backend/tests/test_run_launcher.py`:

```python
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


def test_missing_options_file_yields_defaults(tmp_path) -> None:
    run = _load_run()
    env = run.build_env({}, supervisor_token="t")
    # empty options -> only the always-set keys, no crash
    assert env["CONCIERGE_SKILLS"] == "[]"
    assert env["CONCIERGE_AUTO_RUN_TOOLS"] == "false"
```

- [ ] **Step 2: Run to verify FAIL**

Run: `uv run pytest tests/test_run_launcher.py -v` — FAIL (run.py absent).

- [ ] **Step 3: Implement `homeassistant-addon-concierge-dev/run.py`**

```python
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
import sys
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


def main() -> None:
    options: dict = {}
    if OPTIONS_FILE.is_file():
        try:
            options = json.loads(OPTIONS_FILE.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            _log(f"could not read {OPTIONS_FILE}: {exc}; using defaults")

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        _log("SUPERVISOR_TOKEN not set — HA-backed tools will be unauthenticated")

    os.environ.update(build_env(options, token))
    _log(f"launching concierge (provider={os.environ.get('CONCIERGE_PROVIDER', 'anthropic')})")
    os.execvp("python3", ["python3", "-m", "concierge"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run to verify PASS**

Run: `uv run pytest tests/test_run_launcher.py -v` — 3 PASS. Then `uv run ruff check .` (run.py is one dir up — also `uv run ruff check ../run.py`) and confirm clean.

- [ ] **Step 5: Commit**

```bash
cd ../.. && git add homeassistant-addon-concierge-dev/run.py homeassistant-addon-concierge-dev/backend/tests/test_run_launcher.py
git commit -m "feat(addon): options-to-env launcher for the concierge add-on"
```

---

### Task 3: Options ⇔ Settings parity test

**Files:**
- Test: `homeassistant-addon-concierge-dev/backend/tests/test_addon_config_parity.py`

**Interfaces:**
- Consumes: `config.yaml` (Task 1), `concierge.config.Settings`, `run.py::build_env` (Task 2).
- Produces: the drift guard proving each option maps to a real Settings field, that option defaults construct a valid Settings, and that `build_env` output is accepted by Settings.

- [ ] **Step 1: Write the test**

`homeassistant-addon-concierge-dev/backend/tests/test_addon_config_parity.py`:

```python
"""Guard: config.yaml options must stay in lockstep with Settings.

Options are the operator-facing SUBSET of Settings; these are supplied by the
runtime, not by options, so they're allowed to be absent from config.yaml.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

from concierge.config import Settings

ADDON_DIR = Path(__file__).resolve().parents[2]
MANIFEST = yaml.safe_load((ADDON_DIR / "config.yaml").read_text())

RUNTIME_SUPPLIED = {"ha_url", "ha_token", "data_dir", "host", "port"}


def _load_run():
    spec = importlib.util.spec_from_file_location("addon_run", ADDON_DIR / "run.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_every_option_is_a_settings_field() -> None:
    settings_fields = set(Settings.model_fields)
    unknown = set(MANIFEST["options"]) - settings_fields
    assert not unknown, f"config.yaml options with no Settings field: {unknown}"


def test_no_settings_field_silently_unconfigurable() -> None:
    # Every Settings field is either an exposed option or deliberately
    # runtime-supplied — nothing falls through the cracks unnoticed.
    settings_fields = set(Settings.model_fields)
    unaccounted = settings_fields - set(MANIFEST["options"]) - RUNTIME_SUPPLIED
    assert not unaccounted, (
        f"Settings fields neither exposed as options nor runtime-supplied: "
        f"{unaccounted} — expose them in config.yaml or add to RUNTIME_SUPPLIED"
    )


def test_option_defaults_construct_valid_settings() -> None:
    run = _load_run()
    env = run.build_env(MANIFEST["options"], supervisor_token="tok")
    stripped = {k.removeprefix("CONCIERGE_").lower(): v for k, v in env.items()}
    # Settings parses these from env; feed them directly to prove they validate.
    settings = Settings(**{k: v for k, v in stripped.items() if k in Settings.model_fields})
    assert settings.provider == MANIFEST["options"]["provider"]
```

Note: `Settings(**...)` with string values relies on pydantic coercion for `skills` (a JSON string) and bools. If the constructor rejects the JSON-string `skills`, adapt the test to set the env vars via `monkeypatch.setenv` and call `Settings()` (the real env path) instead of kwargs — keep the assertion that a valid Settings is produced from the manifest defaults.

- [ ] **Step 2: Run**

Run: `uv run pytest tests/test_addon_config_parity.py -v` — 3 PASS (adapt per the note if pydantic coercion differs). If `test_no_settings_field_silently_unconfigurable` fails, that's a real signal: either a Settings field needs exposing in `config.yaml` or adding to `RUNTIME_SUPPLIED` with reason.

- [ ] **Step 3: Full backend suite + commit**

```bash
uv run pytest -q && uv run ruff check . && uv run mypy concierge/
cd ../.. && git add homeassistant-addon-concierge-dev/backend/tests/test_addon_config_parity.py
git commit -m "test(addon): lock config.yaml options to backend Settings"
```

---

### Task 4: Dockerfile (multi-stage) + `.dockerignore`, and a real build

**Files:**
- Create: `homeassistant-addon-concierge-dev/Dockerfile`
- Create: `homeassistant-addon-concierge-dev/.dockerignore`

**Interfaces:**
- Produces: an image that Supervisor can build locally — Node builds `frontend/dist`, `uv` builds the backend venv (with bundled `ha-mcp`), runtime serves via `run.py`.

- [ ] **Step 1: Write `.dockerignore`**

```gitignore
**/__pycache__
**/.pytest_cache
**/.mypy_cache
**/.ruff_cache
backend/.venv
backend/tests
frontend/node_modules
frontend/dist
.superpowers
*.md
```

(`backend/tests` and `*.md` are not needed at runtime; the venv/node_modules/dist are rebuilt in-image.)

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1
# Concierge for HA MCP — built locally by Supervisor from this Dockerfile.
# Multi-stage: Node builds the Lit frontend, uv builds the Python venv
# (backend + bundled ha-mcp), a slim runtime serves both via run.py.

# --- Stage 1: build the Lit frontend -> /fe/dist ---
FROM node:22-slim AS fe-build
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: build the backend venv (backend + ha-mcp) with uv ---
FROM ghcr.io/astral-sh/uv:0.11.27-python3.13-trixie-slim@sha256:68bbb9d4281aa16c9780820ceaf4c558d78fb65ce45d42eb589d7234e3f26e15 AS py-build
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev
COPY backend/concierge ./concierge
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# --- Stage 3: runtime ---
FROM python:3.13-slim@sha256:3de9a8d7aedbb7984dc18f2dff178a7850f16c1ae7c34ba9d7ecc23d0755e35f
WORKDIR /app
COPY --from=py-build /app/.venv /app/.venv
COPY --from=fe-build /fe/dist /app/static
COPY run.py /run.py
ENV PATH="/app/.venv/bin:$PATH" \
    CONCIERGE_STATIC_DIR=/app/static \
    CONCIERGE_DATA_DIR=/data

ARG BUILD_VERSION
ARG BUILD_ARCH
LABEL \
    io.hass.name="Concierge for HA MCP (Dev)" \
    io.hass.description="Self-hosted chat concierge over ha-mcp, served via ingress" \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="${BUILD_ARCH}"

CMD ["python3", "/run.py"]
```

- [ ] **Step 3: Build the image locally** (Docker daemon required — the repo's e2e already relies on it)

Run: `cd homeassistant-addon-concierge-dev && docker build --build-arg BUILD_VERSION=0.1.0.dev1 --build-arg BUILD_ARCH=amd64 -t concierge-addon-smoke:local .`
Expected: build succeeds through all three stages. Common failure modes to fix in place (don't paper over): a frontend build error (the FE must `npm run build` cleanly — it does in Plan 2, so a failure here means a context/path bug), or `uv sync --locked` complaining the lock is stale (regenerate with `uv lock` in `backend/` only if genuinely needed, and commit it).

If Docker is unavailable in this environment, STOP and report BLOCKED — this task's deliverable is a *building* image; do not mark it done on inspection alone.

- [ ] **Step 4: Confirm the image contents**

```bash
docker run --rm --entrypoint sh concierge-addon-smoke:local -c \
  'ls /app/static/index.html && /app/.venv/bin/python -c "import concierge" && /app/.venv/bin/ha-mcp --help >/dev/null 2>&1; echo hamcp=$?'
```
Expected: `index.html` listed, `import concierge` silent (exit 0), `hamcp=0` (the bundled ha-mcp console script resolves in the venv). If `ha-mcp --help` isn't a valid invocation, substitute `/app/.venv/bin/ha-mcp` existence (`test -x`); the point is the stdio entrypoint the backend spawns is present.

- [ ] **Step 5: Commit**

```bash
cd .. && git add homeassistant-addon-concierge-dev/Dockerfile homeassistant-addon-concierge-dev/.dockerignore
git commit -m "feat(addon): multi-stage Dockerfile for the concierge add-on"
```

---

### Task 5: `docker run` smoke — the packaging proof

**Files:**
- Create: `homeassistant-addon-concierge-dev/scripts/smoke.sh` (a committed, re-runnable smoke)

**Interfaces:**
- Consumes: the image from Task 4.
- Produces: a script that runs the image like Supervisor would (options.json in `/data`, ingress port) and asserts the built UI + API serve. This is the end-to-end evidence the add-on actually works when built.

- [ ] **Step 1: Write `homeassistant-addon-concierge-dev/scripts/smoke.sh`**

```bash
#!/usr/bin/env bash
# End-to-end packaging smoke: build (if needed) and run the add-on image the
# way Supervisor would, then assert the built UI and API serve. No live HA:
# ha-mcp lists tools without one; /threads and / need no HA.
set -euo pipefail

ADDON_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE="concierge-addon-smoke:local"
DATA="$(mktemp -d)"
NAME="concierge-smoke-$$"

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; rm -rf "$DATA"; }
trap cleanup EXIT

# Fake add-on options: a dummy key so agent construction (eager provider check)
# succeeds; auto_run_tools true keeps the smoke free of approval prompts.
cat > "$DATA/options.json" <<'JSON'
{"provider":"anthropic","model":"claude-sonnet-5","title_model":"","api_key":"dummy-key",
 "base_url":"","auto_run_tools":true,"skills":[],"tracing":false,"log_level":"info"}
JSON

docker build --build-arg BUILD_VERSION=0.1.0.dev1 --build-arg BUILD_ARCH=amd64 \
  -t "$IMAGE" "$ADDON_DIR" >/dev/null

docker run -d --name "$NAME" -p 8098:8098 -v "$DATA:/data" "$IMAGE" >/dev/null

# Wait for the server (startup spawns the bundled ha-mcp stdio subprocess).
for i in $(seq 1 30); do
  if curl -sf -o /dev/null "http://127.0.0.1:8098/threads"; then break; fi
  sleep 1
  if [ "$i" -eq 30 ]; then echo "server did not start"; docker logs "$NAME"; exit 1; fi
done

echo "== GET /threads =="
threads=$(curl -sf "http://127.0.0.1:8098/threads")
echo "$threads"
[ "$threads" = "[]" ] || { echo "expected [] from a fresh store"; exit 1; }

echo "== GET / (built UI) =="
curl -sf "http://127.0.0.1:8098/" | grep -qi "concierge" || {
  echo "index.html did not serve the built app"; docker logs "$NAME"; exit 1; }

echo "SMOKE OK: built UI served, /threads returns [] — packaging works."
```

`chmod +x homeassistant-addon-concierge-dev/scripts/smoke.sh`

- [ ] **Step 2: Run the smoke**

Run: `homeassistant-addon-concierge-dev/scripts/smoke.sh`
Expected: `SMOKE OK`. Capture the full output in the task report.

Notes for the implementer:
- The container serves at `/` (SPA), `/threads`, `/agui` — the same paths the ingress proxy forwards; hitting the port directly is the faithful local stand-in.
- If startup crashes, `docker logs` will show it. A likely first-run issue: the lifespan `async with agent` enters the bundled ha-mcp toolset (spawns the stdio subprocess + tools/list). That must succeed **without** live HA (Plan 1 Task 11 proved tools/list works with a fake/empty token). If it instead blocks on HA, that's a real finding — report it (the fix would be lazy toolset entry, but Plan 1's design says it shouldn't).
- Do NOT weaken the assertions to make it pass. If the build/run genuinely can't work here (no Docker), report BLOCKED.

- [ ] **Step 3: Commit**

```bash
git add homeassistant-addon-concierge-dev/scripts/smoke.sh
git commit -m "test(addon): end-to-end docker build+run smoke for the concierge add-on"
```

---

## Definition of done (Plan 3)

- `uv run pytest -q` green in `homeassistant-addon-concierge-dev/backend/` (manifest + launcher + parity tests added), ruff + mypy clean.
- `docker build` of `homeassistant-addon-concierge-dev/` succeeds through all three stages.
- `scripts/smoke.sh` prints `SMOKE OK` — the built Lit UI serves at `/` and `/threads` returns `[]` from a fresh store, from the real image.
- Security invariants hold in `config.yaml` (no `ports`, no `host_network`, `ingress_stream: true`) — pinned by `test_addon_manifest.py`.
- All commits on `feat/concierge-addon`; nothing touches master; `backend/`/`frontend/` code unchanged.
- Deferred to **Plan 4** (record in the handoff note if any new fact emerges): the stable flavor dir + slug, the promote sync script, and the version-guard/stable-guard/promote/dev-bump CI workflows. Also note the on-device build cost: Supervisor runs the Node+uv build on the target device (fine on HA Green for this small app; prebuilt ghcr images are the documented scale-up if it bites).
