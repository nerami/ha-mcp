# ha-mcp repo conventions — reference for `homeassistant-addon-concierge/`

Evidence-backed inventory of what this repo already does, for building a new
add-on (FastAPI + Pydantic AI backend, TypeScript/Lit frontend) that feels
native. No changes proposed here — this is a "what IS" document.

---

## 1. Python style

- **Python version floor**: `requires-python = ">=3.13,<3.15"` — `src/`
  targets 3.13; the `<3.15` upper bound exists only so the package still
  installs on HA Core's embedded interpreter (`pyproject.toml:13`,
  comment lines 10-12).
- **Line length 88, ruff-formatted**: `[tool.ruff] line-length = 88`
  (`pyproject.toml:114`); `E501` is explicitly ignored because the
  formatter — not the linter — owns line length (`pyproject.toml:141`).
- **Ruff lint rule set**: `E, W, F, I, B, C4, UP, RUF, PIE, PERF, ASYNC, A,
  LOG, SIM` (`pyproject.toml:124-139`), with a curated ignore list for
  rules the team finds noisier than helpful (e.g. `B008` allowed because
  FastMCP's `Field()`-in-default pattern needs it — `pyproject.toml:142`;
  `SIM102`/`SIM108`/`SIM105` disabled as readability calls —
  `pyproject.toml:144-146`).
- **mypy strict-ish**: `disallow_untyped_defs`, `disallow_incomplete_defs`,
  `check_untyped_defs`, `no_implicit_optional`, `warn_redundant_casts`,
  `warn_unused_ignores`, `warn_return_any` are all on
  (`pyproject.toml:75-83`). Third-party stub-less deps (`fastmcp.*`, `jq`,
  `pydantic_monty`, `homeassistant.*`, `aiohttp`, `voluptuous`, etc.) get
  `ignore_missing_imports = true` overrides (`pyproject.toml:87-109`) —
  the same pattern to follow when adding `pydantic_ai`/`fastapi` stub gaps.
- **Modern typing syntax**: `str | None` unions everywhere, no
  `typing.Optional`/`Union` (e.g. `src/ha_mcp/errors.py:224-226`,
  `src/ha_mcp/tools/helpers.py:81-88`). `from __future__ import annotations`
  used in some but not all modules (`src/ha_mcp/settings_ui/__init__.py:10`,
  `tests/src/unit/conftest.py:19` use it; `src/ha_mcp/errors.py` and
  `src/ha_mcp/tools/tools_areas.py` don't) — not a hard rule, but present
  in newer/larger modules.
- **`StrEnum` for enumerated codes**: `class ErrorCode(StrEnum)` in
  `src/ha_mcp/errors.py:17` — not plain `str, Enum` or a `Literal`.
- **`match`/`case` for multi-branch classification**: used over
  if/elif chains for exhaustive type/status dispatch
  (`src/ha_mcp/tools/helpers.py:204-221` on HTTP status, `:234-260` on
  exception type).
- **Module docstring at top of every file**, one-line summary +
  optional elaboration paragraph, no author/date boilerplate
  (`src/ha_mcp/errors.py:1-11`, `src/ha_mcp/config.py:1-3`,
  `src/ha_mcp/client/rest_client.py:1-3`).
- **Comment-as-rationale, not restatement**: comments explain *why*
  (a workaround, a race, a historical bug number), not what the next
  line does — see the `HomeAssistantAuthError` docstring explaining why
  it's a sibling, not a subclass, of `HomeAssistantAPIError`
  (`src/ha_mcp/client/rest_client.py:51-64`), or the schema-vs-not-found
  branch ordering note in `_classify_by_message`
  (`src/ha_mcp/tools/helpers.py:276-279`). `.gemini/styleguide.md` codifies
  this: "too many comments is an anti-pattern."
- **Docstrings cite issue/discussion numbers** for non-obvious behavior:
  `src/ha_mcp/errors.py:99,103` (`#1569`, `#1579`), `tools_areas.py` module
  header references design rationale inline rather than a tracker link.
- **Logger per module**: `logger = logging.getLogger(__name__)` near the
  top, after imports (`src/ha_mcp/tools/helpers.py:36`,
  `src/ha_mcp/tools/tools_areas.py:33`, `src/ha_mcp/client/rest_client.py:34`).
- **Lazy/local imports to avoid cycles or heavy import-time cost**, always
  commented with the reason: `src/ha_mcp/errors.py:340-342` ("Lazy import
  keeps this low-level module free of an import-time dependency on
  `._version`"), `tests/src/unit/conftest.py:44-47` ("avoid forcing ha_mcp
  import at conftest load time").
- **`NoReturn` + `@overload` for raise-vs-return dual-mode helpers**:
  `exception_to_structured_error` (`src/ha_mcp/tools/helpers.py:380-408`)
  declares two `@overload`s keyed on a `Literal[True]`/`Literal[False]`
  `raise_error` kwarg so mypy narrows the return type per call site.
- **Explicit unreachable-code comments after guaranteed-raise calls**:
  `return None  # unreachable: exception_to_structured_error always raises`
  appears after every `except Exception` block that calls the NoReturn
  helper (`tools_areas.py:383,636,727`) — satisfies mypy's need for an
  explicit return without pretending the line executes.
- **Module size ceiling ~1000 lines** (Pylint's `max-module-lines`
  default) — past that, split by concern and fix internal imports/test
  patch targets (`AGENTS.md` § Module Size). Not universally honored yet
  (`config.py` 1758 lines, `server.py` 1630, `tools_config_helpers.py`
  4095, `settings_ui/__init__.py` 3560) — the rule is aspirational for
  new code, not retroactively enforced.

## 2. Error handling

- **Never construct raw error dicts.** Always go through
  `src/ha_mcp/errors.py` helpers (`create_error_response`,
  `create_entity_not_found_error`, `create_connection_error`,
  `create_auth_error`, `create_service_error`, `create_validation_error`,
  `create_config_error`, `create_timeout_error`) — `AGENTS.md` § Error
  Handling, enforced by `.gemini/styleguide.md` § Structured Error
  Responses (flagged HIGH severity in review if violated).
- **One `StrEnum` of ~38 error codes**, grouped by comment banner
  (`CONNECTION_*`, `AUTH_*`, `ENTITY_*`, ... `SANDBOX_*`, `USER_APPROVAL_*`)
  — `src/ha_mcp/errors.py:32-107`. New error domains get a new banner
  group with a comment explaining why existing codes don't fit
  (e.g. the sandbox and policy-gating groups, `errors.py:84-97`).
- **`DEFAULT_SUGGESTIONS` dict** maps codes to canned actionable
  suggestions (`errors.py:111-218`) so most call sites don't have to
  invent suggestions inline; explicit `suggestions=` overrides win.
- **All tool-level failures raise `ToolError`** via
  `raise_tool_error(create_error_response(...))` (Pattern B) or
  `exception_to_structured_error(e, ...)` (Pattern A, raises by default) —
  never `return {"success": False, ...}` at the top level. Batch-item
  failures inside a `results` list are the sole exception (Pattern D) —
  `AGENTS.md` § Error Handling Patterns A–D.
- **`except ToolError: raise` guard is mandatory** in any `try` block that
  calls `raise_tool_error`/validation helpers, placed before the broad
  `except Exception` — otherwise the broad handler re-wraps a deliberate
  `ToolError` as `INTERNAL_ERROR`. Every tool method in
  `src/ha_mcp/tools/tools_areas.py` follows this
  (`tools_areas.py:368-369, 620-621, 715-716`).
- **Exception classification is layered**: type-based `match`/`case`
  first (`_classify_exception`, `helpers.py:224-266`), falling back to
  message-substring pattern matching (`_classify_by_message`,
  `helpers.py:269-352`) for opaque WebSocket "command failed:" errors
  whose HA Core error code is always `unknown_error`. Ordering matters —
  comments call out "most-specific-first" (`helpers.py:276-279`).
  A parallel dependency-domain classifier would live in the new addon's
  own helpers module, not by extending this one.
- **`warnings` is always a top-level `list[str]`**, never nested in
  `data`, never a singular string (`AGENTS.md` § Return Values;
  contract test `tests/src/unit/test_helper_response_shape.py`).
- **Return-value shape contract**:
  `{"success": True, "data": ...}` / `{"success": True, "data": ..., "warnings": [...]}`
  on success; `raise ToolError(json.dumps({...}))` on tool-level failure;
  `{"success": False, "error": {...}}` only inside a batch results array
  (`AGENTS.md` § Return Values).
- **Platform-specific hint injection point**: `_append_macos_hints`
  (`helpers.py:355-377`) appends extra suggestions to connection errors
  based on `sys.platform`, applied unconditionally at the end of
  `exception_to_structured_error` regardless of caller-supplied
  suggestions — a pattern for injecting environment-specific guidance
  without touching every call site.
- **Add-on-aware error messaging**: `create_auth_error` swaps in
  Supervisor-specific suggestions when `is_running_in_addon()` is true
  (`errors.py:320-349`) rather than showing dead-end "edit your
  HOMEASSISTANT_TOKEN" advice on an add-on install.

## 3. Testing

- **Two top-level suites**: `tests/src/unit/` (fast, mocked clients, no
  Docker) and `tests/src/e2e/` (real containerized HA via
  **testcontainers**, `tests/src/e2e/conftest.py:1-16`, "Tests MUST run
  against this container — never against a real HA instance"). Directory
  is `tests/src/e2e/`, **not** `tests/e2e/` (`AGENTS.md` § Testing).
- **pytest config lives in `pyproject.toml`**:
  `testpaths = ["tests"]`, `--strict-markers --strict-config --verbose
  --tb=short`, `asyncio_mode = "auto"` (`pyproject.toml:165-192`).
  Custom markers are declared and must be registered
  (`slow`, `integration`, `unit`, `automation`, `calendar`, ... ,
  `external_only`, `inaddon_only` — `pyproject.toml:176-191`).
- **Run from `tests/` directory** so the correct `conftest.py` loads:
  `cd tests && uv run pytest src/e2e/ -n2 --dist loadscope -v --tb=short`
  (`AGENTS.md` § Testing). `-n2` locally (each xdist worker spins up its
  own HA container), `-n3` in CI tuned for 2-vCPU runners.
  `tests/.env.test` holds placeholder values only — testcontainers injects
  the real URL dynamically; never hand-set `HOMEASSISTANT_URL`.
- **`conftest.py` fixtures document their own rationale** at module-docstring
  length: `tests/src/unit/conftest.py:1-19` explains *why*
  `enable_auto_backup` defaults off for unit tests (a `MagicMock` client's
  `base_url` breaks `urlparse` inside the auto-backup pre-write hook) and
  how a test opts back in (`monkeypatch.setenv`, auto-reverted).
- **Narrow exception classes inside polling/retry loops**, paired with
  `logger.debug(...)` — never a broad `except Exception` in a retry loop.
  Bugs (`TypeError`, `AttributeError`, `KeyError`, `AssertionError`) must
  propagate so they fail the test instead of retrying to a timeout.
  Codified in `.gemini/styleguide.md` § Exception Handling in Test Polling
  Loops (issue #1266) and `tests/src/e2e/utilities/wait_helpers.py`'s
  `_POLLING_TRANSIENT_ERRORS` tuple.
- **Never assert immediately after creating an entity** — HA needs time to
  register it. Always poll via `tests/src/e2e/utilities/wait_helpers.py`
  helpers: `wait_for_tool_result`, `wait_for_entity_state`,
  `wait_for_condition`, `wait_for_state_change` (`tests/AGENTS.md` §
  E2E Test Patterns).
- **Don't test FastMCP's own schema validation** — it already rejects
  missing required params before the tool body runs; test with valid
  shape but invalid/nonexistent data instead (`tests/AGENTS.md`, explicit
  BAD/GOOD example).
- **Mock clients are small, hand-rolled classes** with just the methods
  the code under test needs (`MockClientWithRegistries` in
  `tests/src/unit/test_area_filter_search.py:19-35`), not a generic
  autospec mock — mirrors the production client's async method surface
  (`get_states`, `get_config`, `base_url` attribute).
- **JS/frontend behavior gets its own JSDOM harness**:
  `tests/src/unit/_js_harness.py` + `run_script()`/`extract_script_body()`
  fake `setTimeout`/`setInterval`/`Date.now`/`fetch`/`BroadcastChannel`,
  used for `settings.js`, Astro `<script>` blocks, and
  `auth/consent_form.py`. Every rendered `<script>` in the repo gets
  automatic parse coverage via `test_rendered_scripts_parse.py`'s
  discovery walker (`_js_harness.py::discover_script_surfaces`) — **no
  manual registration needed** when a new UI surface is added; adding a
  Python-rendered HTML surface only requires registering its renderer in
  `_PY_RENDERERS` (`tests/AGENTS.md` § JS Behaviour Testing). This is the
  direct precedent for testing any hand-rolled JS the new addon ships
  outside a bundler-compiled Lit app.
- **Pre-commit unit-test gate is a subset**: `lefthook.yml`'s
  `unit-tests` job runs only
  `src/unit/ addon/test_addon_startup.py -n auto -m "not slow"` — the
  full e2e suite is not run on every commit, only in CI
  (`e2e-tests.yml`) and on explicit request.
- **Test coverage requirement gate** (`AGENTS.md` § Test Coverage
  Requirements): new MCP tools without E2E tests, core `client`/
  `server.py`/`errors.py` changes without coverage, and all bug fixes
  (TDD: failing regression test first) require tests before merge;
  refactors with existing comprehensive coverage, docs-only changes, and
  minor parameter additions to well-tested tools do not.

## 4. Tooling / CI

- **Lockstep dependency manager**: `uv` everywhere — `uv sync --group
  dev`, `uv run ha-mcp`, `uv lock` (pre-commit hook on `pyproject.toml`
  changes, `lefthook.yml` group 1).
- **`lefthook.yml`** drives pre-commit, two parallel job groups:
  1. `ruff check --fix` + `ruff format` (both `stage_fixed: true`, so the
     fixed file is what gets committed), `ast-grep scan` scoped to
     `src/ha_mcp/tools/**/*.py` only, `uv lock` on `pyproject.toml` touch.
  2. `mypy src/ homeassistant-addon/ scripts/` (a **second**, narrower
     `mypy homeassistant-addon-webhook-proxy/start.py
     homeassistant-addon-webhook-proxy-dev/start.py` job runs in
     parallel — each add-on's `start.py` gets its own mypy invocation
     rather than being folded into the main one), plus the fast unit-test
     subset described above.
  A new addon's Python (`start.py`, backend package) needs to be added to
  the `mypy` glob/target list the same way — either folded into the
  existing `mypy src/` job's target list or given its own parallel job
  like the webhook-proxy add-ons, depending on whether it shares
  `src/ha_mcp`'s mypy config.
- **`--fix` strips unused imports outside `__init__.py`** — when adding an
  import, its first use must land in the *same* commit or lefthook's
  `stage_fixed` ruff pass silently removes it (`AGENTS.md` § Code Quality
  note).
- **Ruff per-file-ignores** carve out narrow exceptions rather than
  loosening the global rule set: `__init__.py` allows `F401` (re-export
  pattern), `tests/**/*` allows `E501`/`B011`, and one named file
  (`tools_config_dashboards.py`) has a `C901` ignore with an inline
  comment pointing at the tracking issue (`pyproject.toml:158-164`) —
  the convention for any future complexity-ignore is: name the exact file,
  cite the issue, and remove the ignore once refactored below threshold.
- **CI workflow map** (`AGENTS.md` § CI/CD Workflows): `pr.yml` (lint +
  type check on every PR), `e2e-tests.yml` (full E2E on PR to master),
  `publish-dev.yml` (dev release every master push),
  `notify-dev-channel.yml`, `semver-release.yml` (biweekly stable cut),
  `release-publish.yml`, `hotfix-release.yml`, `build-binary.yml`,
  `addon-publish.yml`, `sync-tool-docs.yml`.
- **`pr.yml` has a docs/site-only fast path**: a `changes` job classifies
  the diff and skips the heavy E2E lane only when every changed file is
  pure docs/website — add-on directories always count as "code" even for
  doc-only edits inside them (`.github/workflows/pr.yml:24-30` comment).
  A new addon directory should NOT be added to the docs-only skip list.
- **Docker image pinning by digest**: both build and runtime base images
  are pinned with `@sha256:...` digests, not just tags
  (`homeassistant-addon/Dockerfile:8,26`) — renovate-managed via inline
  `# renovate:` comments where relevant (`pr.yml:13`).
- **Gemini Code Assist** reviews every PR automatically per
  `.gemini/styleguide.md` (test coverage, security patterns, tool naming,
  safety annotations, return-value shape, accessibility for web UI
  surfaces). Division of labor with Claude skills documented in
  `AGENTS.md` § Automated Code Review.

## 5. Add-on packaging

- **Every add-on flavor is a fully separate top-level directory** with its
  own `config.yaml`, `Dockerfile`, `DOCS.md`, `CHANGELOG.md`,
  `translations/`: `homeassistant-addon/` (stable, slug `ha_mcp`),
  `homeassistant-addon-dev/` (slug `ha_mcp_dev`),
  `homeassistant-addon-webhook-proxy/` + `-dev` (slug
  `ha_mcp_webhook_proxy[_dev]`). A new `homeassistant-addon-concierge/`
  (and, if it needs a dev channel, `-concierge-dev/`) follows this same
  flat, hand-duplicated-directory pattern — there is no shared/templated
  add-on scaffold in this repo.
- **`config.yaml` shape** (compare
  `homeassistant-addon/config.yaml` vs `-dev/config.yaml`):
  - `name`, `description`, `version` (must match `pyproject.toml`'s
    version for the main ha-mcp addon — `AGENTS.md` § Home Assistant
    Add-on), `slug`, `url`, `arch: [aarch64, amd64]` (no 32-bit — uv's
    base image doesn't build it, `config.yaml:7-10`), `init: false`,
    `startup: application`, `boot: manual` (stable) — dev additionally
    sets `stage: experimental` and `boot: manual`.
  - **`ingress` block** (`ingress: true`, `ingress_port`,
    `ingress_stream: true`) is how the Supervisor's "Open Web UI" button
    works; each comment explains why it must be hand-set per flavor
    (`config.yaml:14-24`) — **the release pipeline only auto-syncs
    version + changelog into `homeassistant-addon/`, never functional
    keys** (`AGENTS.md` § Home Assistant Add-on, "Functional config is
    NOT auto-synced").
  - `hassio_api: true` + `hassio_role: manager` (not `default` —
    `manager` is required for Supervisor log endpoints, verified live,
    issue #1116 — `config.yaml:25-30`), `homeassistant_api: true`,
    `host_network: true` for LAN device discovery, `image:
    "ghcr.io/homeassistant-ai/ha-mcp-addon-{arch}"` (prebuilt, not
    built-on-device — contrast with the webhook-proxy add-ons, which are
    "Built locally by Supervisor from the Dockerfile (no prebuilt
    image)" per `homeassistant-addon-webhook-proxy/AGENTS.md:7-8`).
  - `options:`/`schema:` pairs are declared twice — default values under
    `options`, type constraints under `schema` using HA's schema DSL
    (`bool?`, `int(2,10)?`, `list(strong|normal|weak|auto)`,
    `str?` — `config.yaml:46-72`). Dev-only "beta" feature flags are
    commented with an explicit pointer to `docs/beta.md` explaining why
    they're deliberately NOT mirrored to stable
    (`config.yaml:38-45`).
  - `ports:` maps a fixed internal port (`9583/tcp: 9583`).
- **Dockerfile pattern**: multi-stage — `uv` builder stage
  (`ghcr.io/astral-sh/uv:...python3.13-trixie-slim`, digest-pinned) does
  `uv sync --locked --no-install-project --no-dev` (deps first, cached
  separately from source) then `uv sync --locked --no-dev --no-editable`
  after copying `src/`; runtime stage is bare `python:3.13-slim`
  (digest-pinned) that only copies `/app/.venv` and a `start.py`,
  activates the venv via `PATH`, and sets HA-required `LABEL
  io.hass.*` fields (`homeassistant-addon/Dockerfile:1-51`). `start.py`
  is pure Python (no `bashio`) per file comment line 5.
  `ARG BUILD_VERSION`/`BUILD_ARCH` are threaded through so runtime startup
  logs report the correct version even though the base image doesn't
  know it at build time.
- **`DOCS.md`** is the Supervisor-rendered add-on-store page: `# <Add-on
  Name>` title, one-paragraph `## About` with a feature bullet list,
  `## Installation` numbered steps including the `my.home-assistant.io`
  one-click "Add Repository" badge (`homeassistant-addon/DOCS.md:1-30`).
- **`CHANGELOG.md`** is semantic-release-generated, **never hand-edited**
  (`.gemini/styleguide.md` § Documentation Standards) — versioned
  sections (`## v7.12.0 (date)`) with `### Added`/`### Fixed`/etc.
  subsections linking back to the originating PR, plus a collapsed
  `<details><summary>Internal Changes</summary>` block for
  chore/ci/test commits that don't get their own top-level entry
  (`homeassistant-addon/CHANGELOG.md:1-20`).
- **Dev-first-then-promote is a *webhook-proxy-specific* pattern**, not a
  repo-wide rule for every add-on: the stable ha-mcp add-on
  (`homeassistant-addon/`) DOES get edited directly by PRs (its version
  is synced automatically from `pyproject.toml` on the biweekly release
  cut); only the webhook-proxy add-on enforces "dev tree first, promote
  via workflow, stable never hand-edited" via the
  `webhook-proxy-stable-guard` CI check
  (`homeassistant-addon-webhook-proxy/AGENTS.md` § Dev-first,
  promote-only). Decide which model fits the concierge add-on's release
  cadence explicitly — don't assume one from the other.

## 6. Existing frontend (`settings_ui`) conventions

**This is the key finding for the new Lit frontend: the repo's one
existing in-tree add-on web UI is *not* built with any component
framework, has no JS build step, and is not TypeScript.**

- **Stack**: hand-written **vanilla JavaScript** (`settings.js`, 3731
  lines, no imports, no modules, no framework — confirmed by reading the
  file: plain top-level `let`/`const` globals, `async function`
  declarations, direct DOM API calls) + hand-written **plain CSS**
  (`settings.css`, 970 lines) + a static **HTML template**
  (`settings.html`, 496 lines) with placeholder-substitution markers.
  There is no `package.json`, no bundler, no npm dependency, and no
  TypeScript anywhere under `src/ha_mcp/settings_ui/`.
- **Serving mechanism**: `src/ha_mcp/settings_ui/__init__.py` (3560
  lines) is a Starlette route module. It reads the three static assets
  **once at import time** into module globals (`Path(__file__).parent /
  "settings.html"` etc. — `settings_ui/AGENTS.md` § Gotchas) and performs
  raw string substitution: `__HA_MCP_CSS__`/`__HA_MCP_JS__` are
  filled once at import inside `<style>`/`<script>` tags in the HTML;
  `__HA_MCP_THEME_PREFS__` is filled per-request. Each marker's presence
  is asserted at import so a rename fails fast rather than silently
  serving a broken page.
- **No hot reload**: editing `settings.html`/`.js`/`.css` requires a full
  process restart to see changes (`settings_ui/AGENTS.md` § Gotchas) —
  there is no dev server / watch-mode workflow for this UI today.
- **Design language is HA-native, not ha-mcp-branded**: the page
  deliberately mimics the Home Assistant frontend's own look — `#03a9f4`
  primary, dark blue-grey app toolbar, Roboto, Material cards, hand-replicated
  `ha-switch` geometry (48×24 track, 18px thumb, `--switch-*` CSS custom
  properties), restyled native `<input type="radio">`/`checkbox` via
  `appearance: none` (`settings_ui/AGENTS.md` § Design goal). When unsure
  of a component's geometry, the convention is to read the real
  `home-assistant/frontend` source (e.g. `src/components/ha-switch.ts`)
  rather than guess — "the upstream HA frontend is the source of truth."
- **Talks to backend via `fetch()` against same-origin JSON API
  endpoints** (`./api/settings/features`, `/api/policy/config`, etc.) —
  no client-side router, no state-management library; module-level
  mutable globals (`toolData`, `toolStates`, `policyState`,
  `readOnlyState`) hold UI state (`settings.js:23-60`).
- **Cross-surface JS-logic parity is enforced by test, not by shared
  code**: the theme/accessibility preference-resolution logic in
  `settings.js` must stay *logically* identical to
  `site/src/layouts/Layout.astro` (the separate Astro docs site) — this
  is checked by `tests/src/unit/test_anti_fouc_parity.py`, which compares
  the two independently-maintained implementations rather than sharing a
  module (`settings_ui/AGENTS.md` § Gotchas, "Anti-FOUC parity"). This
  confirms the repo's general pattern of hand-duplicated logic across
  surfaces with a test as the sync mechanism, not a shared package.
- **Accessibility is a first-class, CI-enforced constraint** on this
  surface: native semantic elements over `aria-label` retrofits, one
  `<main>` + `<nav>` landmark, real `role="tablist"`/`tab`/`tabpanel` for
  tab UIs with roving `tabindex` and arrow-key support, `role="status"`
  `aria-live="polite"` for feedback regions escalating to `role="alert"`
  on failure, ordered heading levels — `.gemini/styleguide.md` §
  Accessibility (web UI), backed by the `site-checks` CI job (`astro
  check`, `eslint-plugin-astro` + `jsx-a11y`, axe-core audit — blocking).
- **The only TypeScript / build-tooled frontend in the repo is `site/`**
  (the public docs website), which is a completely separate concern: an
  **Astro** static site (`site/package.json`) with `@astrojs/tailwind`,
  TypeScript via `@astrojs/check`/`typescript`, `eslint` +
  `eslint-plugin-astro` + `eslint-plugin-jsx-a11y`, and its own
  `axe-core`-based a11y audit script. It is not a runtime backend-served
  UI — it's a build-and-deploy static site — so it is a precedent for
  "TypeScript + lint/build tooling conventions" but **not** for "how to
  serve a dynamic app-like UI from the addon backend."

**Conclusion for the new addon**: there is no existing in-repo precedent
for a bundler-built, component-framework (Lit) frontend served by the
Python backend. The `settings_ui` precedent is deliberately
framework-free and build-step-free specifically to (a) minimize
packaging surface (three static files, no `node_modules` in the shipped
wheel) and (b) let a single Starlette module own serving without a
build pipeline dependency. Introducing Lit + a build step for the
concierge addon is a **genuine stack divergence**, not an extension of
an existing pattern — flag it explicitly to the user/reviewer rather
than presenting it as "the same as settings_ui." See the executive
summary for how to reconcile this.

## 7. Commit / release conventions

- **Conventional commits via `python-semantic-release`**
  (`pyproject.toml:220-256`): `commit_parser = "angular"`,
  `major_tags = ["BREAKING", "!"]`, `minor_tags = ["feat"]`,
  `patch_tags = ["fix", "perf", "refactor"]`
  (`pyproject.toml:232-233`). `chore:`/`ci:`/`test:` produce no release;
  `docs:` produces a user-facing changelog entry but no version bump
  (`AGENTS.md` § Release Process table).
  Use the `(internal)` scope (e.g. `feat(internal): ...`) for
  non-user-facing changes so they land in the "Internal Changes"
  collapsed changelog section rather than the user-facing one.
- **Version source of truth**: `version_toml =
  ["pyproject.toml:project.version"]` (`pyproject.toml:221`) — a new
  addon package with its own release cadence would need its own version
  field (its `config.yaml` `version:`, kept in step with whatever
  triggers its release, mirroring how `homeassistant-addon/config.yaml`'s
  `version` is synced from `pyproject.toml` on each stable cut).
- **`branch = "master"`** is the only release branch
  (`pyproject.toml:251`) — **never commit directly to `master`**; all
  work happens in `worktree/<branch-name>` (`AGENTS.md` § Git & PR
  Policies, "CRITICAL - Never commit directly to master").
- **PRs are always opened as drafts** (`gh pr create --draft`) and only
  marked ready on explicit user request, with the PR description updated
  first (`AGENTS.md` § Git & PR Policies).
- **Release cadence**: dev channel republishes every master commit
  (`.devN` suffix via `publish-dev.yml`); stable is cut biweekly
  (Wednesdays 10:00 UTC via `semver-release.yml`), or on-demand via
  manual workflow dispatch (`AGENTS.md` § Release Process).
- **Docker tag discipline**: stable release publishes `:latest` +
  `:stable` + semver tags; dev publishes only `:dev` + `:dev-<sha>` —
  **`:latest` is reserved for stable, never pushed by dev** (`AGENTS.md`
  § CI/CD Workflows, Docker image tags note).
- **Hotfix branches are based on the `stable` tag**, not `master`, and
  must verify the bug actually exists in stable before branching
  (`AGENTS.md` § Hotfix Process).
- **The Boy-Scout-Rule / scope-deferral discipline** (`AGENTS.md` §
  Boy Scout Rule) governs how much unrelated cleanup rides along in a
  PR: small in-scope fixes land silently in the same PR as a separate
  commit; anything that would meaningfully grow the diff or change the
  review surface gets asked about explicitly rather than deferred to a
  follow-up issue unilaterally.

---

## Sources consulted

- `AGENTS.md` (canonical; `CLAUDE.md` is
  a symlink to it)
- `pyproject.toml`
- `lefthook.yml`
- `.gemini/styleguide.md`
- `src/ha_mcp/errors.py`
- `src/ha_mcp/config.py`
- `src/ha_mcp/tools/helpers.py`
- `src/ha_mcp/tools/tools_areas.py`
- `src/ha_mcp/client/rest_client.py`
- `src/ha_mcp/settings_ui/AGENTS.md`
- `src/ha_mcp/settings_ui/__init__.py`
- `src/ha_mcp/settings_ui/settings.js`
- `site/package.json`
- `tests/AGENTS.md`
- `tests/src/unit/conftest.py`
- `tests/src/e2e/conftest.py`
- `tests/src/unit/test_area_filter_search.py`
- `tests/src/e2e/workflows/automation/test_lifecycle.py`
- `homeassistant-addon/config.yaml`
- `homeassistant-addon-dev/config.yaml`
- `homeassistant-addon/Dockerfile`
- `homeassistant-addon/DOCS.md`
- `homeassistant-addon/CHANGELOG.md`
- `homeassistant-addon-webhook-proxy/AGENTS.md`
- `.github/workflows/pr.yml`
