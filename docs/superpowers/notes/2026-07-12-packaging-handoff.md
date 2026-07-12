# Add-on packaging handoff — Plan 3 → Plan 4 (release CI)

Snapshot of `homeassistant-addon-concierge-dev/` packaging state on
`feat/concierge-addon` at the close of Plan 3's whole-phase review. State facts
only — see commit history / review comments for rationale. Plan 4 owns the
stable flavor, the promote/version-guard CI, and the security re-decisions
flagged below.

## Runtime / build facts

- **SUPERVISOR_TOKEN is load-bearing.** An empty `CONCIERGE_HA_TOKEN` makes the
  bundled ha-mcp stdio subprocess fail startup: ha-mcp's standard mode rejects an
  empty/absent token (`_validate_standard_credentials`, `src/ha_mcp/__main__.py`),
  which crashes the add-on. Any Plan-4 CI smoke MUST inject a non-empty
  `-e SUPERVISOR_TOKEN=<non-empty>` (as `scripts/smoke.sh` does). Supervisor
  always injects this for `hassio_api`/`homeassistant_api` add-ons, so real
  installs are unaffected; only out-of-Supervisor runs (CI, `docker run`) must
  supply it.
- **Build freshness** is fixed in the Dockerfile via the project-install step's
  `uv sync ... --reinstall-package concierge-backend`. The backend's version is a
  static `0.0.0` placeholder (the real version lives in `config.yaml`), so uv's
  path-project rebuild key (`pyproject.toml`) never changes and its cache mount
  would otherwise serve a **stale** `concierge-backend@0.0.0` wheel after a
  `concierge/*.py` edit. Note `docker build --no-cache` does NOT clear a
  `RUN --mount=type=cache` cache mount, so `--reinstall-package` (not `--no-cache`)
  is the correct fix; the smoke's build is plain cache-enabled.
- **Supervisor build mechanics.** Supervisor builds via
  `docker buildx build --platform <arch> --pull`, passing `BUILD_VERSION` /
  `BUILD_ARCH` build-args. No `build.yaml` / `BUILD_FROM` is needed. Multi-stage
  builds and `RUN --mount` are supported.
- **On-device build cost.** Supervisor runs `npm ci` + `vite build` + `uv sync`
  on the target device. Acceptable on HA Green for this small app; prebuilt ghcr
  images are the documented scale-up if it bites.

## Plan-4 promote / version-guard facts

- **Version guard** (vs the Webhook Proxy add-on): enforce `.devN` on the dev
  flavor (regex already pinned by `test_dev_version_is_devN`). There is **no
  `manifest.json`** to co-bump — Concierge ships no custom component — so the
  guard watches `config.yaml` only.
- **Promote transform is config-identity only** (backend/frontend code is
  byte-identical across flavors; no token rename). The dev→stable edits are:
  `name`/`description` (drop "(Dev)" / the DEV-channel banner), `slug`
  (`ha_mcp_concierge_dev` → `ha_mcp_concierge`), `panel_title`, drop
  `stage: experimental`, decide `boot:` (Webhook Proxy stable uses `auto`), swap
  the `DOCS.md` banner, and keep a per-flavor `CHANGELOG`.
- **No CI runs the concierge backend tests yet** (`grep concierge .github/workflows/`
  is empty). The manifest security-invariant tests (`test_addon_manifest.py`) are
  **locally enforced only** until Plan 4 wires them in; AGENTS.md's "fails if
  these invariants regress" assumes that wiring.

## Security re-decisions pending (Plan 4)

- **Hassio-network `/agui` reachability**: on the shared hassio docker network,
  any other add-on container can reach `:8098` and drive the unauthenticated
  `/agui` (including approving destructive tools), even with no host port
  published. **Accepted for the dev channel; stable MUST consciously re-decide**
  (ingress-source filtering or a secret path segment, mirroring ha-mcp's
  `MCP_SECRET_PATH`). Cross-ref `homeassistant-addon-concierge-dev/AGENTS.md`
  "Security invariants".
- **`hassio_api` least-privilege review pending**: `config.yaml` keeps
  `hassio_api: true` for the bundled ha-mcp's Supervisor-backed tools (add-on
  management). Concierge's own code never calls the Supervisor API directly
  (skills use DNS). Verify the bundled ha-mcp's actual Supervisor needs on the
  dev channel before promoting.

## Deferred polish

- No `icon.png` / `logo.png` yet — the add-on store shows a generic icon.
- **The frozen backend hardening backlog from `2026-07-10-backend-handoff.md`
  remains open**: full `os.environ` passed into the ha-mcp subprocess, no
  skill-probe timeout, skill resolution is not startup-only, and `skill_name`
  collisions are unguarded.
