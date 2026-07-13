# Add-on packaging handoff — Plan 3 → Plan 4 (release CI)

Snapshot of `homeassistant-addon-concierge-dev/` packaging state on
`feat/concierge-addon` at the close of Plan 3's whole-phase review. State facts
only — see commit history / review comments for rationale. Plan 4 owned the
stable flavor, the promote/version-guard CI, and the security re-decisions
flagged below — see the "DONE" / "RESOLVED" markers below for what Plan 4
closed out; `hassio_api` and the frozen backend hardening backlog remain
open.

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

## Plan-4 promote / version-guard facts — DONE (this plan)

- **Version guard** (vs the Webhook Proxy add-on): enforce `.devN` on the dev
  flavor (regex already pinned by `test_dev_version_is_devN`). There is **no
  `manifest.json`** to co-bump — Concierge ships no custom component — so the
  guard watches `config.yaml` only. **Implemented**:
  `.github/workflows/concierge-dev-version-guard.yml`.
- **Promote transform is config-identity only** (backend/frontend code is
  byte-identical across flavors; no token rename). **Implemented**:
  `scripts/concierge_sync.py` performs the dev→stable edits (`name`/
  `description`, `slug` `ha_mcp_concierge_dev` → `ha_mcp_concierge`,
  `panel_title`, drop `stage: experimental`, `boot:`, Dockerfile labels, doc
  framing); `tests/src/unit/test_concierge_sync.py` is the drift test proving
  code stays byte-identical and security invariants survive. Promotion itself
  runs via `.github/workflows/concierge-promote.yml` (**"Concierge — Promote
  Dev to Stable"**, `workflow_dispatch`), opening a draft PR on
  `promote-concierge/<version>`. Stable is guarded against direct edits by
  `.github/workflows/concierge-stable-guard.yml`; routine dev bumps go through
  `.github/workflows/concierge-dev-bump.yml` (**"Concierge Dev — Bump
  Version"**).
- **CI now runs the concierge backend tests**: `.github/workflows/concierge-tests.yml`
  runs backend, frontend, sync-drift, and docker-smoke jobs on add-on PRs. The
  manifest security-invariant tests (`test_addon_manifest.py`) are now
  **CI-enforced**, not just local; AGENTS.md's "fails if these invariants
  regress" holds in CI.

## Security re-decisions — `/agui` RESOLVED, `hassio_api` still open

- **Hassio-network `/agui` reachability — RESOLVED by the ingress guard.** On
  the shared hassio docker network, any other add-on container could
  previously reach `:8098` and drive the unauthenticated `/agui` (including
  approving destructive tools), even with no host port published.
  `backend/concierge/ingress_guard.py` closes this via source-IP enforcement:
  a pure-ASGI middleware wired into `create_app` (`web.py`) resolves the
  `supervisor` hostname's IPs at startup and 403s any request whose real TCP
  peer isn't a resolved Supervisor IP. It is **permissive when the allow-set
  is empty** (`supervisor` doesn't resolve — dev/CI/docker), so it never
  breaks non-Supervisor runs, and it logs whether it's active or permissive at
  startup. This closure is real only where `supervisor` resolves — see the
  live-verification item in `homeassistant-addon-concierge-dev/AGENTS.md`'s
  pre-first-promote checklist, item 1.
- **`hassio_api` least-privilege review — still OPEN**: `config.yaml` keeps
  `hassio_api: true` for the bundled ha-mcp's Supervisor-backed tools (add-on
  management). Concierge's own code never calls the Supervisor API directly
  (skills use DNS). Verify the bundled ha-mcp's actual Supervisor needs on the
  dev channel before promoting. Now cross-referenced from the
  `homeassistant-addon-concierge-dev/AGENTS.md` pre-first-promote checklist,
  item 2 — this must resolve before the first stable cut.

## Deferred polish

- No `icon.png` / `logo.png` yet — the add-on store shows a generic icon. Now
  cross-referenced as optional item 5 in the
  `homeassistant-addon-concierge-dev/AGENTS.md` pre-first-promote checklist.
- **The frozen backend hardening backlog from `2026-07-10-backend-handoff.md`
  remains OPEN** (not part of this plan's scope): full `os.environ` passed
  into the ha-mcp subprocess, no skill-probe timeout, skill resolution is not
  startup-only, and `skill_name` collisions are unguarded.
