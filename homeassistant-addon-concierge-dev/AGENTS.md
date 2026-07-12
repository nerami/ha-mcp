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
transform is config-identity only — the `backend/`/`frontend/` code is
byte-identical across flavors (no token rename).
