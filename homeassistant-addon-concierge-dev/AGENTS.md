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

## Developing

Two independent subprojects with their own toolchains — neither is covered by
the root `src/` lint or the root `tests/` (testcontainers) suite.

**Backend** (run from `homeassistant-addon-concierge-dev/backend/`):
```bash
uv sync --group dev
uv run pytest
uv run ruff check .
uv run mypy concierge/
```
Style: ruff line-length 88, mypy `disallow_untyped_defs`, `X | None` unions, no
broad `except` inside polling loops. Use **Pydantic AI v2 APIs only**:
`MCPToolset` + `fastmcp` transports (never the deprecated `MCPServerStdio` /
`MCPServerStreamableHTTP`); the `.prefixed()` / `.approval_required()`
combinators; `DeferredToolRequests` / `DeferredToolResults` (never
`DeferredToolCalls`).

**Frontend** (run from `homeassistant-addon-concierge-dev/frontend/`):
```bash
npm install
npx vitest run
npm run lint
npm run typecheck
npm run build
```
Constraints: runtime deps are closed to `lit`, `marked`, `dompurify` (no React,
no `@ag-ui/client` / RxJS); **all API paths are RELATIVE** (`./agui`,
`./threads`) because the app is served under Supervisor ingress's dynamic
prefix.

Pre-commit (lefthook) runs the `mypy-concierge` and `frontend-concierge` jobs
scoped to these directories.

## References

- `docs/superpowers/notes/2026-07-10-backend-handoff.md` — the verified AG-UI
  wire contract (SSE events, HITL resume shape, thread rehydration).
- `homeassistant-addon-concierge-dev/frontend/README.md` — frontend dev
  workflow (Vite dev proxy).
- `docs/superpowers/notes/2026-07-12-packaging-handoff.md` — packaging facts,
  the `hassio_api` least-privilege review, and the frozen backend hardening
  backlog (known gaps in `agent.py` / `skills.py`).
- `docs/superpowers/specs/2026-07-09-concierge-addon-design.md` — the design
  spec.

## Security invariants (do not weaken)
`/agui` has no authentication — ingress is the auth boundary. The manifest
therefore has **no `ports:` and no `host_network:`**; the UI is reachable only
through Supervisor's ingress proxy. `homeassistant-addon-concierge-dev/backend/tests/test_addon_manifest.py`
fails if any of these invariants regress.

**Hassio-network reachability — closed by the ingress guard.** On the shared
hassio docker network, any other add-on container could previously reach
`:8098` and drive the unauthenticated `/agui` (including approving destructive
tools), even with no host port published. `backend/concierge/ingress_guard.py`
closes this: a pure-ASGI middleware wired into `create_app` (`web.py`) that
resolves the `supervisor` hostname's IPs at startup and 403s any HTTP request
whose real TCP peer (`scope["client"][0]`) is not a resolved Supervisor IP.

**Live-verification gate.** The guard is **permissive when the allow-set is
empty** — i.e. whenever `supervisor` doesn't resolve (dev/CI/docker runs
outside Supervisor), so it never breaks a non-Supervisor run. It only actively
enforces where `supervisor` *does* resolve, which means the closure above is
real only once verified live on the dev channel under real Supervisor DNS. On
startup it logs whether it is active (Supervisor IP resolved) or permissive —
see the **Pre-first-promote checklist** below, item 1.

## Release: dev-first / promote-only

Dev (`homeassistant-addon-concierge-dev/`) is canonical; every change bumps
`config.yaml`'s `version` (format `X.Y.Z.devN`), enforced by
**`concierge-dev-version-guard.yml`** (PR check: the bump must strictly
increase). Stable (`homeassistant-addon-concierge/`) is never hand-edited —
**`concierge-stable-guard.yml`** blocks direct edits to it unless the PR comes
from a `promote-concierge/*` branch or carries the `allow-stable-edit` label
(this file and its `CLAUDE.md` symlink are exempted). Stable is produced
solely by the **Concierge — Promote Dev to Stable** workflow
(`workflow_dispatch`; `.github/workflows/concierge-promote.yml`), which runs
`scripts/concierge_sync.py --direction promote --bump <level>`, runs
`tests/src/unit/test_concierge_sync.py` as the acceptance gate (proves
backend/frontend code stays byte-identical across flavors and the security
invariants above survive the transform), and opens a **draft** PR on
`promote-concierge/<version>`. Use **Concierge Dev — Bump Version**
(`workflow_dispatch`; `.github/workflows/concierge-dev-bump.yml`) for routine
dev-only version bumps (opens a draft PR touching `config.yaml` only).
`concierge-tests.yml` runs the backend, frontend, sync-drift, and
docker-smoke jobs in CI on add-on PRs.

No stable directory exists yet — it is produced by the first `promote`
dispatch, gated on the checklist below.

## Pre-first-promote checklist

Before the first stable cut (first `concierge-promote.yml` dispatch), all of
the following must be true:

1. **Ingress guard live-verified.** A live dev-channel test confirms the guard
   admits real Supervisor ingress traffic with no false 403 — capture the
   startup "ingress guard active — Supervisor at …" log line and a working UI
   load through ingress.
2. **`hassio_api` least-privilege resolved.** Verify whether the bundled
   ha-mcp actually needs `hassio_api: true` on the dev channel; drop it from
   `config.yaml` if not.
3. **Stable `boot:` chosen** (default `auto`, matching the Webhook Proxy
   stable add-on).
4. **Stable `CHANGELOG.md` written.**
5. **Icon/logo** (`icon.png`/`logo.png`) — optional polish, not blocking.

See `docs/superpowers/notes/2026-07-12-packaging-handoff.md` for the
`hassio_api` review and the frozen backend hardening backlog this checklist
cross-references.

## Options ⇔ Settings
`config.yaml` options are the operator-facing subset of `concierge.config.Settings`
(`ha_url`/`ha_token`/`data_dir`/`host`/`port` are supplied by the runtime, not
options). `test_addon_config_parity.py` enforces that every option maps to a
real Settings field.

## Versioning & flavors
`config.yaml` `version` (format `X.Y.Z.devN`) is the single release id; bump it
on every change (see "Release" above for the guard that enforces this). Only
the **dev** flavor is committed today — the **stable** flavor
(`homeassistant-addon-concierge/`, slug `ha_mcp_concierge`) is produced by the
promote workflow, not hand-written. Because Concierge installs no custom
component, the dev↔stable transform is config-identity only — the
`backend/`/`frontend/` code is byte-identical across flavors (no token
rename); see `scripts/concierge_sync.py`.
