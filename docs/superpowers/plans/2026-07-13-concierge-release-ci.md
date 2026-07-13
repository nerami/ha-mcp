# Concierge Release CI + Ingress Guard Implementation Plan (Plan 4 of 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Concierge add-on releasable and safe for a stable channel: (1) an **ingress-source guard** that rejects any request not arriving through Supervisor's ingress proxy — closing the co-resident-add-on hole on the unauthenticated `/agui`; (2) the **dev-first / promote-only** release machinery (a config-identity sync script + version-guard, stable-guard, promote, and dev-bump workflows) mirroring the Webhook Proxy add-on; and (3) **CI** that runs the concierge backend, frontend, and docker smoke on every add-on PR.

**Architecture:** The guard is a FastAPI HTTP middleware in the backend: it resolves the Supervisor container's IP(s) at app startup and 403s any request whose real TCP peer isn't Supervisor — staying permissive when `supervisor` doesn't resolve (dev/CI/local `docker run`), so it never bricks a non-Supervisor run. The release machinery is a Python `scripts/concierge_sync.py` (regex text transforms on `config.yaml`/`Dockerfile`/docs — no YAML round-trip, so comments survive; no token rename, since backend/frontend code is byte-identical across flavors) plus four GitHub workflows. CI adds a `concierge-tests.yml` running the two suites + the docker smoke + the sync drift test.

**Tech Stack:** FastAPI/Starlette middleware · stdlib `socket` · Python `scripts/concierge_sync.py` (stdlib + `re`) · pytest (backend uv env + root `tests/src/unit` with `ruamel.yaml`) · GitHub Actions (transcribed from `homeassistant-addon-webhook-proxy*` workflows).

**Scope:** Plans 1–3 (backend, frontend, packaging) are complete. This plan adds the guard (a small, well-scoped backend addition) + release CI. It does **not** commit a stable flavor dir — the first `homeassistant-addon-concierge/` is produced by the *promote* workflow's first dispatch, after (a) live dev-channel testing confirms the ingress guard doesn't block real ingress and (b) the `hassio_api` least-privilege review. Those are recorded as explicit pre-first-promote gates.

**Authorities:** `docs/superpowers/notes/2026-07-12-packaging-handoff.md` (the Plan-4 fact sheet). `homeassistant-addon-webhook-proxy/AGENTS.md` + the four `webhook-proxy-*.yml` workflows + `scripts/webhook_proxy_sync.py` (the pattern being mirrored). Spec §7-8.

## Global Constraints

- **Ingress-guard correctness is paramount — a false positive bricks the add-on** (blank UI). The guard MUST be permissive whenever it cannot positively identify a Supervisor source (`supervisor` unresolvable → dev/CI/`docker run`), log its mode at startup, and log every rejection with the offending source IP. It uses the **real TCP peer** (`request.client.host`) — never a forgeable `X-Forwarded-For`/`X-Ingress-Path` header — as the trust signal. Non-optional (no "disable" toggle that would undermine it); if it misfires it gets fixed, and live dev-channel verification is a pre-stable-promote gate.
- **Release model = dev-first / promote-only** (mirrors Webhook Proxy): a PR never edits `homeassistant-addon-concierge/` (stable) directly except from a `promote-concierge/*` branch or with the `allow-stable-edit` label (AGENTS.md/CLAUDE.md exempted). Every change lands on `homeassistant-addon-concierge-dev/` first, with a `config.yaml` version bump the dev-version-guard enforces.
- **Promote transform is config-identity only.** Concierge ships no custom component, so backend/frontend/`run.py`/`Dockerfile`(-modulo-labels) are **byte-identical** across flavors — the sync must NOT mutate them. The dev→stable edits are exactly: `config.yaml` (`slug` `ha_mcp_concierge_dev`→`ha_mcp_concierge`; `name`/`description` drop "(Dev)"/the DEV-channel banner; `panel_title` drop "(Dev)"; drop `stage: experimental`; `boot: manual`→`auto`; `version`→ independent stable `X.Y.Z`), `Dockerfile` LABELs (drop "(Dev)"), and the `AGENTS.md`/`DOCS.md` dev-framing. `CHANGELOG.md` is per-flavor (manual on the promote PR).
- **Version formats:** dev `X.Y.Z.devN` (pinned by `test_dev_version_is_devN`); stable `X.Y.Z` (no `.devN`). No `manifest.json` (no component) — the version guard watches `config.yaml` only.
- **Sync uses regex text transforms**, not `yaml.load`/`dump` — comments and formatting must survive. The drift **test** may parse YAML for assertions (root `tests/src/unit` env has `ruamel.yaml`).
- Backend changes (guard) run in `homeassistant-addon-concierge-dev/backend/` (ruff 88, mypy `disallow_untyped_defs`, existing 70 tests must stay green). Workflows are transcribed faithfully from the `webhook-proxy-*.yml` originals with the concierge renames + the documented simplifications. Commits on `feat/concierge-addon`, never master. Conventional commits.

---

### Task 1: Ingress-source guard (backend)

**Files:**
- Create: `homeassistant-addon-concierge-dev/backend/concierge/ingress_guard.py`
- Modify: `homeassistant-addon-concierge-dev/backend/concierge/web.py` (wire the middleware into `create_app`, after `app = FastAPI(...)` at line 67)
- Test: `homeassistant-addon-concierge-dev/backend/tests/test_ingress_guard.py`

**Interfaces:**
- Produces: `resolve_supervisor_ips(host: str = "supervisor") -> frozenset[str]` (getaddrinfo → IP set; empty on `gaierror`/failure) and `install_ingress_guard(app: FastAPI, *, allowed_ips: frozenset[str]) -> None` (registers an HTTP middleware that 403s when `allowed_ips` is non-empty and the request's peer isn't in it; permissive when empty). `create_app` calls `install_ingress_guard(app, allowed_ips=resolve_supervisor_ips())` once.

- [ ] **Step 1: Write the failing test**

`tests/test_ingress_guard.py`:

```python
import socket

from fastapi import FastAPI
from fastapi.testclient import TestClient

from concierge import ingress_guard


def _app(allowed: frozenset[str]) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    def ping() -> dict[str, bool]:
        return {"ok": True}

    ingress_guard.install_ingress_guard(app, allowed_ips=allowed)
    return app


def test_permissive_when_no_supervisor_resolved() -> None:
    # Empty allow-set = dev/CI/docker-run: everything passes.
    with TestClient(_app(frozenset())) as c:
        assert c.get("/ping").status_code == 200


def test_rejects_peer_not_in_allowset() -> None:
    # TestClient's peer host is "testclient"; an allow-set without it => 403.
    with TestClient(_app(frozenset({"172.30.32.2"}))) as c:
        resp = c.get("/ping")
        assert resp.status_code == 403


def test_allows_peer_in_allowset() -> None:
    with TestClient(_app(frozenset({"testclient"}))) as c:
        assert c.get("/ping").status_code == 200


def test_resolve_supervisor_ips_empty_on_unknown_host(monkeypatch) -> None:
    def boom(*a: object, **k: object) -> object:
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    assert ingress_guard.resolve_supervisor_ips() == frozenset()


def test_resolve_supervisor_ips_collects_addresses(monkeypatch) -> None:
    def fake(host, *a, **k):  # type: ignore[no-untyped-def]
        assert host == "supervisor"
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.32.2", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.32.2", 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert ingress_guard.resolve_supervisor_ips() == frozenset({"172.30.32.2"})
```

- [ ] **Step 2: Run to verify FAIL**

Run: `cd homeassistant-addon-concierge-dev/backend && uv run pytest tests/test_ingress_guard.py -v`
Expected: FAIL (`concierge.ingress_guard` missing).

- [ ] **Step 3: Implement `concierge/ingress_guard.py`**

```python
"""Reject requests that did not arrive through Supervisor's ingress proxy.

The add-on publishes no host port and binds only the ingress port, but on the
shared `hassio` docker network any co-resident add-on can still reach that port
directly and drive the unauthenticated `/agui` (including approving destructive
tools). Legitimate traffic always arrives via Supervisor, which proxies the
final hop — so its real TCP peer is the Supervisor container. A co-resident
add-on connecting directly presents its own peer IP and cannot spoof it at the
socket layer (unlike an `X-Ingress-Path` header, which it could forge).

The guard resolves Supervisor's IP(s) at startup. If it can't (no `supervisor`
DNS name — i.e. a dev box, CI, or a plain `docker run`), it stays PERMISSIVE:
there is no ingress to enforce there, and a false rejection would brick the UI.
"""

from __future__ import annotations

import logging
import socket
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def resolve_supervisor_ips(host: str = "supervisor") -> frozenset[str]:
    """The Supervisor container's IP(s); empty when the host can't resolve."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return frozenset()
    return frozenset(info[4][0] for info in infos)


def install_ingress_guard(app: FastAPI, *, allowed_ips: frozenset[str]) -> None:
    """403 any request whose peer isn't Supervisor. No-op when allowed is empty."""
    if not allowed_ips:
        logger.warning(
            "ingress guard PERMISSIVE — Supervisor not resolvable "
            "(dev/CI/standalone run); not enforcing request source"
        )
    else:
        logger.info("ingress guard active — Supervisor at %s", sorted(allowed_ips))

    @app.middleware("http")
    async def _guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if allowed_ips:
            peer = request.client.host if request.client else None
            if peer not in allowed_ips:
                logger.warning(
                    "ingress guard rejected %s %s from non-Supervisor peer %s",
                    request.method,
                    request.url.path,
                    peer,
                )
                return JSONResponse(
                    {"error": "forbidden: reach this add-on through Home Assistant"},
                    status_code=403,
                )
        return await call_next(request)
```

- [ ] **Step 4: Wire it into `create_app`** (`concierge/web.py`, right after `app = FastAPI(title="concierge", lifespan=lifespan)`)

```python
    app = FastAPI(title="concierge", lifespan=lifespan)
    # Only Supervisor's ingress proxy may reach this app (see ingress_guard).
    install_ingress_guard(app, allowed_ips=resolve_supervisor_ips())
```

Add the import at the top of `web.py`: `from concierge.ingress_guard import install_ingress_guard, resolve_supervisor_ips`.

- [ ] **Step 5: Run guard tests + full backend suite**

Run: `uv run pytest tests/test_ingress_guard.py -v` (5 PASS). Then the FULL suite: `uv run pytest -q` — must stay green (the existing 70 tests run outside Supervisor → `supervisor` unresolvable → guard permissive → no regression). Then `uv run ruff check .`, `uv run mypy concierge/`.

- [ ] **Step 6: Re-run the packaging smoke** (the guard is now in the served app; the smoke runs outside Supervisor → permissive → must still `SMOKE OK`)

Run: `../scripts/smoke.sh` → `SMOKE OK`. If it 403s, the permissive fallback is broken — fix it (do not weaken the guard). Note: bump the dev `config.yaml` version (`0.1.0.dev1` → `0.1.0.dev2`) since this changes add-on behavior — the dev-version-guard (Task 4) will later enforce this, and it's correct to start now.

- [ ] **Step 7: Commit**

```bash
cd ../.. && git add homeassistant-addon-concierge-dev/backend/concierge/ingress_guard.py \
  homeassistant-addon-concierge-dev/backend/concierge/web.py \
  homeassistant-addon-concierge-dev/backend/tests/test_ingress_guard.py \
  homeassistant-addon-concierge-dev/config.yaml
git commit -m "feat(concierge): ingress-source guard rejecting non-Supervisor requests"
```

---

### Task 2: Promote sync script

**Files:**
- Create: `scripts/concierge_sync.py`

**Interfaces:**
- Produces: `python scripts/concierge_sync.py --direction promote --bump patch|minor|major` — copies `homeassistant-addon-concierge-dev/` → `homeassistant-addon-concierge/`, applies the config-identity transforms, sets the stable version, prints it. `--direction reset` copies stable→dev (pulls a stable hotfix back), re-adding dev identity + a `.devN` version. Pure functions `transform_config(text, *, to_stable, version) -> str`, `transform_dockerfile(text, *, to_stable) -> str`, `transform_docs(text, *, to_stable) -> str`, `next_stable_version(current_stable, dev_version, bump) -> str` are unit-testable.

- [ ] **Step 1: Read the reference**

Read `scripts/webhook_proxy_sync.py` for structure (version parse/bump helpers, `transform_config_yaml`, `apply_dockerfile_labels`, `sync`, `main`). Concierge's is a strict subset: **no** `rename_tokens`/`apply_start_py_identity`/`apply_manifest` (no component, no manifest) and **no** per-file component rename — only config/Dockerfile/docs identity + version.

- [ ] **Step 2: Implement `scripts/concierge_sync.py`**

```python
#!/usr/bin/env python3
"""Sync the Concierge add-on between its dev and stable flavors.

Concierge ships no custom component, so backend/frontend/run.py/Dockerfile
(minus LABELs) are byte-identical across flavors — this transform touches only
flavor IDENTITY (config.yaml, Dockerfile labels, doc framing) and the version.
Regex text edits (not YAML round-trip) so comments/formatting survive.

  --direction promote --bump {patch,minor,major}   dev -> stable
  --direction reset                                 stable -> dev (hotfix pull)
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_DIR = REPO_ROOT / "homeassistant-addon-concierge-dev"
STABLE_DIR = REPO_ROOT / "homeassistant-addon-concierge"

DEV_SLUG = "ha_mcp_concierge_dev"
STABLE_SLUG = "ha_mcp_concierge"
# Files whose CONTENT must never differ between flavors (no identity in them).
# Everything else is copied verbatim; identity files are transformed below.
_CODE_DIRS = ("backend", "frontend")


def _read_version(config_text: str) -> str:
    m = re.search(r'^version:\s*"([^"]+)"', config_text, re.M)
    if not m:
        raise ValueError("no version in config.yaml")
    return m.group(1)


def next_stable_version(current_stable: str | None, dev_version: str, bump: str) -> str:
    """First promote (no stable yet) => dev's X.Y.Z; else bump the stable line."""
    if current_stable is None:
        m = re.match(r"^(\d+)\.(\d+)\.(\d+)", dev_version)
        if not m:
            raise ValueError(f"unparseable dev version: {dev_version!r}")
        return f"{m[1]}.{m[2]}.{m[3]}"
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", current_stable)
    if not m:
        raise ValueError(f"unparseable stable version: {current_stable!r}")
    major, minor, patch = int(m[1]), int(m[2]), int(m[3])
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def next_dev_version(stable_version: str) -> str:
    """reset: start a fresh dev line from the stable base."""
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", stable_version)
    if not m:
        raise ValueError(f"unparseable stable version: {stable_version!r}")
    return f"{m[1]}.{m[2]}.{m[3]}.dev1"


def transform_config(text: str, *, to_stable: bool, version: str) -> str:
    if to_stable:
        text = text.replace(f'slug: "{DEV_SLUG}"', f'slug: "{STABLE_SLUG}"')
        text = text.replace("Concierge for HA MCP (Dev)", "Concierge for HA MCP")
        text = text.replace(
            'description: "DEV CHANNEL (unstable) — ',
            'description: "',
        )
        text = text.replace('panel_title: "Concierge (Dev)"', 'panel_title: "Concierge"')
        text = re.sub(r"^stage:\s*experimental\n", "", text, flags=re.M)
        text = re.sub(r"^boot:\s*manual\b", "boot: auto", text, flags=re.M)
    else:  # reset: stable -> dev identity
        text = text.replace(f'slug: "{STABLE_SLUG}"', f'slug: "{DEV_SLUG}"')
        text = text.replace("Concierge for HA MCP", "Concierge for HA MCP (Dev)")
        text = text.replace('description: "', 'description: "DEV CHANNEL (unstable) — ')
        text = text.replace('panel_title: "Concierge"', 'panel_title: "Concierge (Dev)"')
        text = re.sub(r"^boot:\s*auto\b", "boot: manual", text, flags=re.M)
        # re-add stage: experimental after the boot line
        text = re.sub(r"^(boot:\s*manual\n)", r"\1stage: experimental\n", text, flags=re.M)
    text = re.sub(r'^version:\s*"[^"]+"', f'version: "{version}"', text, count=1, flags=re.M)
    return text


def transform_dockerfile(text: str, *, to_stable: bool) -> str:
    if to_stable:
        return text.replace(
            'io.hass.name="Concierge for HA MCP (Dev)"',
            'io.hass.name="Concierge for HA MCP"',
        )
    return text.replace(
        'io.hass.name="Concierge for HA MCP"',
        'io.hass.name="Concierge for HA MCP (Dev)"',
    )


def transform_docs(text: str, *, to_stable: bool) -> str:
    """Swap the '(dev flavor)' framing in AGENTS.md/DOCS.md."""
    if to_stable:
        return text.replace(" (dev flavor)", "").replace("(Dev)", "").replace(
            "DEV CHANNEL (unstable) — ", ""
        )
    # reset is rare; the dev-side framing is restored by re-running the dev edit
    # by hand on the reset PR if needed. Keep reset a copy for code, manual docs.
    return text


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)


def sync(direction: str, bump: str | None, root: Path = REPO_ROOT) -> str:
    dev, stable = root / DEV_DIR.name, root / STABLE_DIR.name
    to_stable = direction == "promote"
    src, dst = (dev, stable) if to_stable else (stable, dev)

    dev_version = _read_version((dev / "config.yaml").read_text())
    current_stable = (
        _read_version((stable / "config.yaml").read_text()) if stable.exists() else None
    )
    if to_stable:
        assert bump is not None
        version = next_stable_version(current_stable, dev_version, bump)
    else:
        assert current_stable is not None
        version = next_dev_version(current_stable)

    _copy_tree(src, dst)  # verbatim code copy; identity files fixed up below
    (dst / "config.yaml").write_text(
        transform_config((dst / "config.yaml").read_text(), to_stable=to_stable, version=version)
    )
    (dst / "Dockerfile").write_text(
        transform_dockerfile((dst / "Dockerfile").read_text(), to_stable=to_stable)
    )
    for doc in ("AGENTS.md", "DOCS.md"):
        p = dst / doc
        if p.exists() and not p.is_symlink():
            p.write_text(transform_docs(p.read_text(), to_stable=to_stable))
    # CHANGELOG.md is per-flavor: restore the destination's own (don't carry src's).
    changelog_src = src / "CHANGELOG.md"
    if changelog_src.exists() and (dst_prev := _stashed_changelog.get(dst.name)):
        (dst / "CHANGELOG.md").write_text(dst_prev)
    return version


# Preserve the destination flavor's own CHANGELOG across the copytree.
_stashed_changelog: dict[str, str] = {}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--direction", required=True, choices=["promote", "reset"])
    p.add_argument("--bump", choices=["patch", "minor", "major"])
    args = p.parse_args(argv)
    if args.direction == "promote" and not args.bump:
        p.error("--bump is required for --direction promote")
    # Stash the destination CHANGELOG before the copytree clobbers it.
    dst_name = STABLE_DIR.name if args.direction == "promote" else DEV_DIR.name
    dst_changelog = REPO_ROOT / dst_name / "CHANGELOG.md"
    if dst_changelog.exists():
        _stashed_changelog[dst_name] = dst_changelog.read_text()
    version = sync(args.direction, args.bump)
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note for the implementer: the CHANGELOG-preservation via a module global is awkward — if you find a cleaner shape (e.g. stash inside `sync()` before `_copy_tree`), use it; the contract is "the destination flavor keeps its own CHANGELOG.md, code files are copied verbatim, identity files are transformed." Verify the exact `config.yaml` strings this transforms against the real Task-1 `config.yaml` (the `description:` prefix, the `panel_title`, the `name`) — adjust the literals to match byte-for-byte; a substring that doesn't match silently no-ops.

- [ ] **Step 3: Smoke the script by hand into a scratch dir** (do NOT commit a stable dir)

```bash
python3 scripts/concierge_sync.py --direction promote --bump patch
git status --short homeassistant-addon-concierge/    # a generated stable tree appears
# inspect: slug, no stage:, boot: auto, version 0.1.0, name without (Dev)
grep -E 'slug:|version:|boot:|stage:|^name:' homeassistant-addon-concierge/config.yaml
git checkout . ; git clean -fd homeassistant-addon-concierge/   # discard — stable is created by the real promote later
```

- [ ] **Step 4: Commit the script**

```bash
git add scripts/concierge_sync.py
git commit -m "feat(ci): concierge dev<->stable config-identity sync script"
```

---

### Task 3: Sync drift-guard test

**Files:**
- Create: `tests/src/unit/test_concierge_sync.py`

**Interfaces:**
- Consumes: `scripts/concierge_sync.py`.
- Produces: tests (root uv env; `ruamel.yaml` available) that run the promote transform in a **tmp** repo copy and assert the invariants — without needing a committed stable dir.

- [ ] **Step 1: Write the test**

`tests/src/unit/test_concierge_sync.py`:

```python
"""Promote-transform drift guards. Concierge's transform is config-identity
only: code must be byte-identical across flavors; only identity/version change.
"""

import filecmp
import importlib.util
import shutil
from pathlib import Path

import pytest
from ruamel.yaml import YAML

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV = REPO_ROOT / "homeassistant-addon-concierge-dev"


def _load_sync():
    spec = importlib.util.spec_from_file_location(
        "concierge_sync", REPO_ROOT / "scripts" / "concierge_sync.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def promoted(tmp_path: Path):
    """Copy dev into a tmp repo, run promote, return (tmp_root, sync_module)."""
    sync = _load_sync()
    root = tmp_path / "repo"
    (root / DEV.name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DEV, root / DEV.name, symlinks=True)
    version = sync.sync("promote", "patch", root=root)
    return root, version


def _yaml(path: Path) -> dict:
    return YAML(typ="safe").load(path.read_text())


def test_stable_identity(promoted) -> None:
    root, version = promoted
    cfg = _yaml(root / "homeassistant-addon-concierge" / "config.yaml")
    assert cfg["slug"] == "ha_mcp_concierge"
    assert "stage" not in cfg
    assert cfg["boot"] == "auto"
    assert "(Dev)" not in cfg["name"]
    assert "DEV CHANNEL" not in cfg["description"]
    assert cfg["version"] == version
    import re

    assert re.match(r"^\d+\.\d+\.\d+$", version), "stable version must have no .devN"


def test_security_invariants_survive_promote(promoted) -> None:
    root, _ = promoted
    cfg = _yaml(root / "homeassistant-addon-concierge" / "config.yaml")
    assert cfg.get("ingress") is True
    assert cfg.get("ingress_stream") is True
    assert "ports" not in cfg
    assert cfg.get("host_network") is not True


def test_code_is_byte_identical_across_flavors(promoted) -> None:
    root, _ = promoted
    dev, stable = root / "homeassistant-addon-concierge-dev", root / "homeassistant-addon-concierge"
    for rel in ("backend/concierge", "frontend/src", "run.py"):
        cmp = filecmp.dircmp(dev / rel, stable / rel) if (dev / rel).is_dir() else None
        if cmp is not None:
            assert not cmp.diff_files and not cmp.left_only and not cmp.right_only, (
                f"{rel} differs between flavors: {cmp.diff_files or cmp.left_only or cmp.right_only}"
            )
        else:
            assert (dev / rel).read_text() == (stable / rel).read_text(), f"{rel} differs"


def test_dockerfile_differs_only_in_labels(promoted) -> None:
    root, _ = promoted
    dev = (root / "homeassistant-addon-concierge-dev" / "Dockerfile").read_text().splitlines()
    stable = (root / "homeassistant-addon-concierge" / "Dockerfile").read_text().splitlines()
    diff = [(a, b) for a, b in zip(dev, stable, strict=True) if a != b]
    assert all("io.hass.name" in a for a, _ in diff), f"Dockerfile drift beyond labels: {diff}"
```

Note: `filecmp.dircmp` doesn't recurse into subdirs by default — if `backend/concierge` has subpackages, also assert `cmp.subdirs` recursively, or use `filecmp.cmpfiles`/a walk. Make the byte-identical check genuinely recursive; that invariant is the whole point.

- [ ] **Step 2: Run** (root uv env)

Run: `cd <repo root> && uv run pytest tests/src/unit/test_concierge_sync.py -v` — all PASS. If the promote transform leaves any code file different across flavors, this fails loudly (correct).

- [ ] **Step 3: Commit**

```bash
git add tests/src/unit/test_concierge_sync.py
git commit -m "test(ci): concierge promote-transform drift guards"
```

---

### Task 4: `concierge-dev-version-guard` workflow

**Files:**
- Create: `.github/workflows/concierge-dev-version-guard.yml`

**Interfaces:**
- Produces: a PR check that fails any PR touching `homeassistant-addon-concierge-dev/**` without bumping `config.yaml` `version` (which must be `X.Y.Z.devN` and strictly increase). Simpler than webhook-proxy's — **no `manifest.json` parity** (Concierge has no component).

- [ ] **Step 1: Write the workflow** (adapt `webhook-proxy-dev-version-guard.yml`; drop the manifest/parity half)

```yaml
name: Concierge Dev — Version Guard

on:
  pull_request:
    paths:
      - "homeassistant-addon-concierge-dev/**"

permissions:
  contents: read

jobs:
  require-version-bump:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - name: Require a dev version bump (X.Y.Z.devN, increasing)
        env:
          BASE_REF: ${{ github.base_ref }}
        run: |
          set -euo pipefail
          BASE="origin/$BASE_REF"
          CFG=homeassistant-addon-concierge-dev/config.yaml
          ver() { python3 -c 'import sys,re;m=re.search(r"^version:\s*\"([^\"]+)\"",open(sys.argv[1]).read(),re.M);print(m.group(1) if m else "")' "$1"; }
          NEW=$(ver "$CFG")
          OLD=$(git show "$BASE:$CFG" 2>/dev/null | python3 -c 'import sys,re;m=re.search(r"^version:\s*\"([^\"]+)\"",sys.stdin.read(),re.M);print(m.group(1) if m else "")' || true)
          if [ -z "$OLD" ]; then echo "New dev add-on (no base version) — OK."; exit 0; fi
          if [ "$NEW" = "$OLD" ]; then
            echo "::error::homeassistant-addon-concierge-dev changed but version is still $NEW — bump it."
            exit 1
          fi
          python3 - "$OLD" "$NEW" <<'PY'
          import re, sys
          def key(v):
              m = re.match(r"^(\d+)\.(\d+)\.(\d+)\.dev(\d+)$", v)
              if not m: sys.exit(f"::error::dev version must be X.Y.Z.devN, got {v!r}")
              return (int(m[1]), int(m[2]), int(m[3]), int(m[4]))
          old, new = sys.argv[1], sys.argv[2]
          if key(new) <= key(old):
              sys.exit(f"::error::dev version must increase: {old} -> {new}")
          print(f"dev version bump OK: {old} -> {new}")
          PY
```

- [ ] **Step 2: Validate the YAML parses + commit**

```bash
python3 -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/concierge-dev-version-guard.yml').read_text())" || uvx yq . .github/workflows/concierge-dev-version-guard.yml >/dev/null
git add .github/workflows/concierge-dev-version-guard.yml
git commit -m "ci(concierge): dev version guard"
```

(If `yaml`/`yq` unavailable, any equivalent YAML parse is fine. Do not skip validation.)

---

### Task 5: `concierge-stable-guard` workflow

**Files:**
- Create: `.github/workflows/concierge-stable-guard.yml`

**Interfaces:**
- Produces: blocks PRs editing `homeassistant-addon-concierge/**` unless from a `promote-concierge/*` branch or carrying `allow-stable-edit`; exempts `AGENTS.md`/`CLAUDE.md` (in their regular-file + symlink shape).

- [ ] **Step 1: Write the workflow** — transcribe `webhook-proxy-stable-guard.yml` verbatim, replacing every `webhook-proxy` path with `concierge`, the branch prefix `promote-webhook-proxy/` → `promote-concierge/`, and the two exempt paths with `homeassistant-addon-concierge/AGENTS.md` + `homeassistant-addon-concierge/CLAUDE.md`. Keep the fail-closed diff, the `grep -vxF` exemption, and the AGENTS/CLAUDE shape check (mode 100644 + 120000 symlink → AGENTS.md) exactly. Keep the `types: [opened, synchronize, reopened, labeled, unlabeled]`.

- [ ] **Step 2: Validate YAML + commit**

```bash
python3 -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/concierge-stable-guard.yml').read_text())"
git add .github/workflows/concierge-stable-guard.yml
git commit -m "ci(concierge): stable guard (promote-only)"
```

---

### Task 6: `concierge-promote` + `concierge-dev-bump` workflows

**Files:**
- Create: `.github/workflows/concierge-promote.yml`
- Create: `.github/workflows/concierge-dev-bump.yml`

**Interfaces:**
- Produces: `workflow_dispatch` promote (runs `concierge_sync.py --direction promote --bump`, runs the drift test as the acceptance gate, opens a draft PR on `promote-concierge/<version>`) and dev-bump (bumps `config.yaml` to `X.Y.Z.devN`, opens a draft PR).

- [ ] **Step 1: Write `concierge-promote.yml`** (adapt `webhook-proxy-promote.yml`; the drift gate is `tests/src/unit/test_concierge_sync.py`, no `WEBHOOK_PROXY_TREES_SYNCED` env)

```yaml
name: Concierge — Promote Dev to Stable

on:
  workflow_dispatch:
    inputs:
      bump:
        description: "Semver bump for the new stable version"
        type: choice
        default: patch
        options: [patch, minor, major]

permissions:
  contents: write
  pull-requests: write

jobs:
  promote:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v6
      - name: Run the promote transform in place
        id: promote
        run: |
          set -euo pipefail
          NEW=$(python3 scripts/concierge_sync.py --direction promote --bump "${{ inputs.bump }}")
          echo "version=$NEW" >> "$GITHUB_OUTPUT"
      - name: Verify transform exactness (drift guards)
        run: uv run pytest tests/src/unit/test_concierge_sync.py -q
      - name: Commit on a branch and open a draft PR
        env:
          GH_TOKEN: ${{ github.token }}
          BASE_REF: ${{ github.ref_name }}
          NEW_VERSION: ${{ steps.promote.outputs.version }}
        run: |
          set -euo pipefail
          BRANCH="promote-concierge/$NEW_VERSION"
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git checkout -b "$BRANCH"
          git add homeassistant-addon-concierge/
          git commit -m "chore(addon): promote concierge dev -> stable $NEW_VERSION"
          git push -u origin "$BRANCH"
          gh pr create --draft --base "$BASE_REF" --head "$BRANCH" \
            --title "chore(addon): promote concierge dev -> stable $NEW_VERSION" \
            --body "Generated by the concierge-promote workflow. Config-identity transform of the dev flavor onto stable (slug/name/boot/stage/version + Dockerfile labels + doc framing); backend/frontend byte-identical. CHANGELOG.md and the two security re-decisions (ingress-guard live verification, hassio_api least-privilege) are for the human reviewer."
```

- [ ] **Step 2: Write `concierge-dev-bump.yml`** (adapt `webhook-proxy-dev-bump.yml`; drop the manifest co-bump — only `config.yaml`)

```yaml
name: Concierge Dev — Bump Version

on:
  workflow_dispatch:
    inputs:
      level:
        description: "Which part to bump"
        type: choice
        default: dev
        options: [dev, patch, minor, major]

permissions:
  contents: write
  pull-requests: write

jobs:
  bump:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Bump dev version in config.yaml
        env:
          LEVEL: ${{ inputs.level }}
        run: |
          set -euo pipefail
          python3 - "$LEVEL" <<'PY'
          import re, sys, pathlib
          level = sys.argv[1]
          cfg = pathlib.Path("homeassistant-addon-concierge-dev/config.yaml")
          text = cfg.read_text()
          cur = re.search(r'^version:\s*"([^"]+)"', text, re.M).group(1)
          m = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:\.dev(\d+))?$", cur)
          if not m: sys.exit(f"unparseable version: {cur!r}")
          major, minor, patch = int(m[1]), int(m[2]), int(m[3])
          dev = int(m[4]) if m[4] is not None else 0
          new = {"dev": f"{major}.{minor}.{patch}.dev{dev+1}",
                 "patch": f"{major}.{minor}.{patch+1}.dev1",
                 "minor": f"{major}.{minor+1}.0.dev1",
                 "major": f"{major+1}.0.0.dev1"}[level]
          cfg.write_text(re.sub(r'^version:\s*"[^"]+"', f'version: "{new}"', text, count=1, flags=re.M))
          print(f"bumped {cur} -> {new}")
          PY
      - name: Open a PR
        env:
          GH_TOKEN: ${{ github.token }}
          BASE_REF: ${{ github.ref_name }}
        run: |
          set -euo pipefail
          NEW=$(python3 -c 'import re;print(re.search(r"^version:\s*\"([^\"]+)\"",open("homeassistant-addon-concierge-dev/config.yaml").read(),re.M).group(1))')
          BRANCH="chore/concierge-dev-bump-$NEW"
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git checkout -b "$BRANCH"
          git add homeassistant-addon-concierge-dev/config.yaml
          git commit -m "chore(addon-dev): bump concierge-dev to $NEW"
          git push -u origin "$BRANCH"
          gh pr create --draft --base "$BASE_REF" --head "$BRANCH" \
            --title "chore(addon-dev): bump concierge-dev to $NEW" \
            --body "Manual dev version bump to \`$NEW\`."
```

- [ ] **Step 3: Validate both YAMLs + commit**

```bash
for f in concierge-promote concierge-dev-bump; do python3 -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/$f.yml').read_text())"; done
git add .github/workflows/concierge-promote.yml .github/workflows/concierge-dev-bump.yml
git commit -m "ci(concierge): promote and dev-bump workflows"
```

---

### Task 7: CI — run the concierge suites + smoke on add-on PRs

**Files:**
- Create: `.github/workflows/concierge-tests.yml`

**Interfaces:**
- Produces: the CI gate that actually runs the concierge backend + frontend suites (incl. the manifest security-invariant tests, previously local-only) + a `docker build`/smoke, on PRs touching the add-on. Closes the handoff's "no CI runs the concierge tests yet" gap.

- [ ] **Step 1: Write `concierge-tests.yml`**

```yaml
name: Concierge — Tests

on:
  pull_request:
    paths:
      - "homeassistant-addon-concierge-dev/**"
      - "scripts/concierge_sync.py"
      - "tests/src/unit/test_concierge_sync.py"
      - ".github/workflows/concierge-tests.yml"

permissions:
  contents: read

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: homeassistant-addon-concierge-dev/backend
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v6
      - run: uv sync --group dev
      - run: uv run pytest -q
      - run: uv run ruff check . && uv run ruff check ../run.py
      - run: uv run mypy concierge/

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: homeassistant-addon-concierge-dev/frontend
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npx vitest run
      - run: npm run build

  sync-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v6
      - run: uv run pytest tests/src/unit/test_concierge_sync.py -q

  docker-smoke:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - name: Build + run the add-on image the way Supervisor would
        run: homeassistant-addon-concierge-dev/scripts/smoke.sh
```

Note: confirm the repo's convention for `setup-uv` (the promote/bump workflows above assume `astral-sh/setup-uv@v6` provides `uv`; if the repo pins a different action/version, match it — check an existing workflow like `e2e-tests.yml`). The `sync-drift` job runs `uv run` at repo root; ensure the root `pyproject.toml`'s env resolves (it has `ruamel.yaml`). If the root `uv run pytest` needs a group sync first, add `uv sync` before it.

- [ ] **Step 2: Validate YAML + commit**

```bash
python3 -c "import yaml,pathlib; yaml.safe_load(pathlib.Path('.github/workflows/concierge-tests.yml').read_text())"
git add .github/workflows/concierge-tests.yml
git commit -m "ci(concierge): run backend, frontend, sync-drift, and docker smoke on add-on PRs"
```

---

### Task 8: Docs — live promote flow, guard, and the pre-promote gates

**Files:**
- Modify: `homeassistant-addon-concierge-dev/AGENTS.md`
- Modify: `docs/superpowers/notes/2026-07-12-packaging-handoff.md`
- Modify: `docs/superpowers/specs/2026-07-09-concierge-addon-design.md` (§8 status)

**Interfaces:**
- Produces: docs reflecting that the release machinery + ingress guard now exist, and a crisp **pre-first-promote checklist**.

- [ ] **Step 1: Update the add-on `AGENTS.md`**
  - "Security invariants" section: the hassio-network `/agui` hole is now **closed by `ingress_guard.py`** (source-IP == Supervisor; permissive off-Supervisor). Note the guard's live-verification gate below.
  - Add a "Release: dev-first / promote-only" section: dev is canonical; `config.yaml` `version` bumps on every change (guarded); stable is produced by the **Concierge — Promote Dev to Stable** workflow (`workflow_dispatch`); stable is never hand-edited (guarded), `AGENTS.md`/`CLAUDE.md` exempted; use **Concierge Dev — Bump Version** for dev bumps. Cross-ref `scripts/concierge_sync.py`.
  - Add a **Pre-first-promote checklist** (must be true before the first stable cut): (1) live dev-channel test confirms the ingress guard admits real ingress traffic (no false 403) — capture the startup "ingress guard active — Supervisor at …" log and a working UI; (2) `hassio_api` least-privilege resolved (verified whether bundled ha-mcp actually needs it; drop if not); (3) pick the stable `boot:` (default `auto`); (4) write the stable `CHANGELOG.md` entry; (5) optional icon/logo.

- [ ] **Step 2: Update the handoff note** — mark the promote/version-guard/CI items as **done** (this plan), and the `/agui` re-decision as **resolved by the ingress guard** (source-IP enforcement); leave the `hassio_api` review and the frozen backend hardening backlog as open, now cross-referenced from the AGENTS.md pre-promote checklist.

- [ ] **Step 3: Update spec §8** — note the promote automation + guard now exist (Plan 4); the two-flavor dev-first model is live.

- [ ] **Step 4: Commit**

```bash
git add homeassistant-addon-concierge-dev/AGENTS.md docs/superpowers/notes/2026-07-12-packaging-handoff.md docs/superpowers/specs/2026-07-09-concierge-addon-design.md
git commit -m "docs(concierge): document the live promote flow, ingress guard, and pre-promote gates"
```

---

## Definition of done (Plan 4)

- **Ingress guard:** `uv run pytest -q` green in the backend (existing 70 + 5 guard tests), ruff + mypy clean; the guard is wired into `create_app`, is permissive off-Supervisor, and the packaging smoke still prints `SMOKE OK`.
- **Release machinery:** `scripts/concierge_sync.py` promotes dev→stable as config-identity-only; `tests/src/unit/test_concierge_sync.py` passes and proves code is byte-identical across flavors + security invariants survive; all four workflows (`dev-version-guard`, `stable-guard`, `promote`, `dev-bump`) exist and parse as valid YAML, faithfully mirroring the Webhook Proxy originals with the concierge renames.
- **CI:** `concierge-tests.yml` runs the backend, frontend, sync-drift, and docker-smoke jobs on add-on PRs — the manifest security-invariant tests are now CI-enforced.
- **Docs:** AGENTS.md documents the live promote flow + guard + the pre-first-promote checklist; the handoff note and spec §8 are updated.
- **No stable dir committed** — it is produced by the first `promote` dispatch, gated on the AGENTS.md pre-promote checklist. All commits on `feat/concierge-addon`; nothing on master; Plans 1–3 code unchanged except the guard addition to `web.py`.
