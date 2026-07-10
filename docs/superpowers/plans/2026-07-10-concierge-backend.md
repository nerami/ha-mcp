# Concierge Backend Implementation Plan (Plan 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Concierge add-on's Python backend: a Pydantic AI agent whose tools come from a bundled ha-mcp MCP server (stdio) plus optional skill add-ons (HTTP MCP), streaming turns to clients over the AG-UI protocol with annotation-derived human-in-the-loop tool approval and SQLite thread persistence.

**Architecture:** A self-contained uv project at `homeassistant-addon-concierge-dev/backend/` (mirrors the webhook-proxy pattern: code lives in the addon dir, own lint/test cycle). FastAPI serves one AG-UI run endpoint (`POST /agui`) via Pydantic AI's `AGUIAdapter` with a persistence tee, plus thread CRUD. AG-UI is client-owns-messages: each `RunAgentInput` carries the thread's messages; the server tees the event stream into SQLite for cross-session rehydration.

**Tech Stack:** Python 3.13 · `pydantic-ai-slim[ag-ui,mcp]==2.8.0` · `ha-mcp==7.12.0` · FastAPI + uvicorn · pydantic-settings · SQLite (WAL) · pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-07-09-concierge-addon-design.md` (approved). Plan 2 = Lit frontend; Plan 3 = addon packaging/CI. This plan yields a standalone, testable, runnable service.

## Global Constraints

- Python **3.13** (`requires-python = ">=3.13"`).
- Pins: `pydantic-ai-slim[ag-ui,mcp]==2.8.0`, `ha-mcp==7.12.0`. Backend `version = "0.0.0"` stays static (addon `config.yaml` owns the real version — repo convention).
- **v2 APIs only:** `from pydantic_ai.mcp import MCPToolset`; `from fastmcp.client.transports import StdioTransport` (fastmcp is a dependency of pydantic-ai-slim[mcp] — do NOT import StdioTransport from pydantic_ai); `DeferredToolRequests`/`DeferredToolResults` (NOT the removed `DeferredToolCalls`); `.prefixed()`/`.approval_required()` combinators (NOT `tool_prefix=`); never `MCPServerStdio`/`MCPServerStreamableHTTP` (deprecated).
- Bundled ha-mcp toolset is **never** `.prefixed()` (tools are already `ha_*`); each skill toolset is `.prefixed(<slug with - → _>)`.
- `.approval_required()` wraps the **raw** MCPToolset (innermost), before any prefixing.
- Approval gating: `readOnlyHint` → auto-run; otherwise `destructiveHint` (default **True** when absent — fail-safe); `auto_run_tools=True` disables gating entirely.
- Persistence: AG-UI-format messages (camelCase JSON), one SQLite write per turn at stream end. No `pending_approvals` table. No `ModelMessagesTypeAdapter`.
- Style: ruff line-length 88; mypy `disallow_untyped_defs`; `X | None` unions; no broad `except` inside polling loops; every commit from the worktree on branch `feat/concierge-addon` (never master).
- Default models: chat `anthropic:claude-sonnet-5`, titles `anthropic:claude-haiku-4-5` (operator-overridable options).
- All commands below run from `homeassistant-addon-concierge-dev/backend/` unless stated otherwise.

---

### Task 1: Project scaffold + Settings

**Files:**
- Create: `homeassistant-addon-concierge-dev/backend/pyproject.toml`
- Create: `homeassistant-addon-concierge-dev/backend/concierge/__init__.py`
- Create: `homeassistant-addon-concierge-dev/backend/concierge/config.py`
- Create: `homeassistant-addon-concierge-dev/backend/tests/__init__.py`
- Test: `homeassistant-addon-concierge-dev/backend/tests/test_config.py`

**Interfaces:**
- Produces: `concierge.config.Settings` (pydantic-settings model, env prefix `CONCIERGE_`) with fields `provider: str = "anthropic"`, `model: str = "claude-sonnet-5"`, `title_model: str | None = None`, `api_key: str = ""`, `base_url: str | None = None`, `auto_run_tools: bool = False`, `skills: list[str] = []`, `ha_url: str = ""`, `ha_token: str = ""`, `data_dir: Path = Path("/data")`, `host: str = "0.0.0.0"`, `port: int = 8098`, `log_level: str = "info"`, `tracing: bool = False`; and `load_settings() -> Settings`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "concierge-backend"
# Static placeholder — the add-on's real version lives in config.yaml (repo
# convention; keeps Docker dependency-layer caching intact).
version = "0.0.0"
description = "Concierge add-on backend: Pydantic AI agent over ha-mcp, streaming AG-UI"
requires-python = ">=3.13"
dependencies = [
    "pydantic-ai-slim[ag-ui,mcp]==2.8.0",
    "ha-mcp==7.12.0",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "pydantic-settings>=2.6",
]

[dependency-groups]
dev = [
    "pytest>=8.4",
    "pytest-asyncio>=1.1",
    "httpx>=0.28",
    "mypy>=1.14",
    "ruff>=0.9",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["concierge*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 88
target-version = "py313"

[tool.mypy]
python_version = "3.13"
disallow_untyped_defs = true
warn_return_any = true
warn_unused_ignores = true
```

- [ ] **Step 2: Write the failing test**

`tests/test_config.py`:

```python
from pathlib import Path

from concierge.config import Settings, load_settings


def test_defaults() -> None:
    s = Settings()
    assert s.provider == "anthropic"
    assert s.model == "claude-sonnet-5"
    assert s.title_model is None
    assert s.auto_run_tools is False
    assert s.skills == []
    assert s.data_dir == Path("/data")
    assert s.port == 8098
    assert s.tracing is False


def test_env_overrides(monkeypatch) -> None:
    monkeypatch.setenv("CONCIERGE_MODEL", "gpt-5")
    monkeypatch.setenv("CONCIERGE_PROVIDER", "openai")
    monkeypatch.setenv("CONCIERGE_AUTO_RUN_TOOLS", "true")
    monkeypatch.setenv("CONCIERGE_SKILLS", '["pixoo","http://x:9000/mcp"]')
    s = load_settings()
    assert (s.provider, s.model) == ("openai", "gpt-5")
    assert s.auto_run_tools is True
    assert s.skills == ["pixoo", "http://x:9000/mcp"]


def test_effective_title_model_falls_back() -> None:
    assert Settings().effective_title_model == "claude-haiku-4-5"
    assert Settings(title_model="m").effective_title_model == "m"
    # explicit chat model but no title model -> default title model still used
    assert Settings(model="x").effective_title_model == "claude-haiku-4-5"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd homeassistant-addon-concierge-dev/backend && uv sync && uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'concierge'` (or ImportError).

- [ ] **Step 4: Implement `concierge/config.py`** (and empty `concierge/__init__.py`, `tests/__init__.py`)

```python
"""Runtime settings, populated from CONCIERGE_* environment variables.

The add-on run script maps config.yaml options onto these variables; in dev
they are set directly. `skills` accepts a JSON list (pydantic-settings parses
complex types from JSON).
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_TITLE_MODEL = "claude-haiku-4-5"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CONCIERGE_")

    provider: str = "anthropic"
    model: str = "claude-sonnet-5"
    title_model: str | None = None
    api_key: str = ""
    base_url: str | None = None
    auto_run_tools: bool = False
    skills: list[str] = []
    ha_url: str = ""
    ha_token: str = ""
    data_dir: Path = Path("/data")
    host: str = "0.0.0.0"
    port: int = 8098
    log_level: str = "info"
    # OTel instrumentation toggle; export target comes from the standard
    # OTEL_EXPORTER_OTLP_* env vars (Langfuse/Logfire both consume OTLP).
    tracing: bool = False

    @property
    def effective_title_model(self) -> str:
        return self.title_model or DEFAULT_TITLE_MODEL


def load_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 PASS.

- [ ] **Step 6: Lint, type-check, commit**

```bash
uv run ruff check . && uv run ruff format . && uv run mypy concierge/
cd ../..   # repo root of the worktree
git add homeassistant-addon-concierge-dev/backend
git commit -m "feat(concierge): scaffold backend project with settings"
```

---

### Task 2: Model builder

**Files:**
- Create: `concierge/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: `Settings` (Task 1).
- Produces: `build_model(settings: Settings) -> Model | str` and `build_title_model(settings: Settings) -> Model | str`. Native providers return the `"provider:model"` string form (setting the provider's conventional API-key env var when `api_key` is provided); a `base_url` returns `OpenAIChatModel` against any OpenAI-compatible endpoint.

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:

```python
import os

from pydantic_ai.models.openai import OpenAIChatModel

from concierge.config import Settings
from concierge.models import build_model, build_title_model


def test_native_provider_returns_string_form(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    s = Settings(provider="anthropic", model="claude-sonnet-5", api_key="sk-x")
    assert build_model(s) == "anthropic:claude-sonnet-5"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-x"


def test_api_key_env_not_clobbered_when_empty(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "preset")
    s = Settings(provider="openai", model="gpt-5", api_key="")
    build_model(s)
    assert os.environ["OPENAI_API_KEY"] == "preset"


def test_base_url_builds_openai_compatible_model() -> None:
    s = Settings(model="qwen3", base_url="http://ollama.local:11434/v1", api_key="k")
    model = build_model(s)
    assert isinstance(model, OpenAIChatModel)


def test_title_model_uses_same_provider() -> None:
    s = Settings(provider="anthropic")
    assert build_title_model(s) == "anthropic:claude-haiku-4-5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'concierge.models'`.

- [ ] **Step 3: Implement `concierge/models.py`**

```python
"""Map generic provider options onto a Pydantic AI model.

Native providers use the "provider:model" string form (Pydantic AI resolves
credentials from the provider's conventional env var, which we set from the
generic `api_key` option). A `base_url` switches to OpenAIChatModel against
any OpenAI-compatible endpoint (Ollama, OpenRouter, vLLM, ...).
"""

from __future__ import annotations

import os

from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from concierge.config import Settings

_API_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


def _build(settings: Settings, model_name: str) -> Model | str:
    if settings.base_url:
        return OpenAIChatModel(
            model_name,
            provider=OpenAIProvider(
                base_url=settings.base_url,
                api_key=settings.api_key or "unused",
            ),
        )
    env_var = _API_KEY_ENV.get(settings.provider)
    if env_var and settings.api_key:
        os.environ[env_var] = settings.api_key
    return f"{settings.provider}:{model_name}"


def build_model(settings: Settings) -> Model | str:
    return _build(settings, settings.model)


def build_title_model(settings: Settings) -> Model | str:
    return _build(settings, settings.effective_title_model)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check . && uv run mypy concierge/
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "feat(concierge): provider-agnostic model builder"
```

---

### Task 3: Approval gating predicate

**Files:**
- Create: `concierge/gating.py`
- Test: `tests/test_gating.py`

**Interfaces:**
- Produces: `is_destructive(tool_def: ToolDefinition) -> bool` and `approval_callback(ctx: object, tool_def: ToolDefinition, tool_args: dict[str, object]) -> bool` (the exact signature `.approval_required()` calls). Reads MCP annotations from `tool_def.metadata["annotations"]`, tolerating both dict and object annotation shapes.

- [ ] **Step 1: Write the failing test**

`tests/test_gating.py`:

```python
from pydantic_ai.tools import ToolDefinition

from concierge.gating import approval_callback, is_destructive

SCHEMA = {"type": "object", "properties": {}}


def _td(annotations: object) -> ToolDefinition:
    return ToolDefinition(
        name="t",
        parameters_json_schema=SCHEMA,
        metadata={"annotations": annotations} if annotations is not None else None,
    )


def test_read_only_is_not_gated() -> None:
    assert is_destructive(_td({"readOnlyHint": True})) is False


def test_destructive_is_gated() -> None:
    assert is_destructive(_td({"destructiveHint": True})) is True


def test_explicit_non_destructive_write_is_not_gated() -> None:
    assert is_destructive(_td({"destructiveHint": False})) is False


def test_missing_annotations_default_to_gated() -> None:
    assert is_destructive(_td(None)) is True
    assert is_destructive(_td({})) is True


def test_object_style_annotations_supported() -> None:
    class Ann:
        readOnlyHint = True
        destructiveHint = None

    assert is_destructive(_td(Ann())) is False


def test_approval_callback_matches_predicate() -> None:
    assert approval_callback(None, _td({"readOnlyHint": True}), {}) is False
    assert approval_callback(None, _td(None), {}) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gating.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'concierge.gating'`.

- [ ] **Step 3: Implement `concierge/gating.py`**

```python
"""Derive approval-required status from MCP safety annotations.

Policy: readOnlyHint -> auto-run; otherwise destructiveHint decides, and a
missing hint means gated (the MCP default for destructiveHint is true, and
fail-safe is the right default for un-annotated tools).
"""

from __future__ import annotations

from pydantic_ai.tools import ToolDefinition


def _get(annotations: object, key: str) -> object:
    if isinstance(annotations, dict):
        return annotations.get(key)
    return getattr(annotations, key, None)


def is_destructive(tool_def: ToolDefinition) -> bool:
    annotations = (tool_def.metadata or {}).get("annotations")
    if annotations is None:
        return True
    if _get(annotations, "readOnlyHint"):
        return False
    destructive = _get(annotations, "destructiveHint")
    return True if destructive is None else bool(destructive)


def approval_callback(
    ctx: object, tool_def: ToolDefinition, tool_args: dict[str, object]
) -> bool:
    """Signature expected by `toolset.approval_required(...)`."""
    return is_destructive(tool_def)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_gating.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check . && uv run mypy concierge/
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "feat(concierge): annotation-derived approval gating"
```

---

### Task 4: Skill endpoint resolution + probing

**Files:**
- Create: `concierge/skills.py`
- Test: `tests/test_skills.py`

**Interfaces:**
- Consumes: `Settings.skills` (Task 1).
- Produces: `repo_prefix(hostname: str) -> str | None`, `skill_endpoint(entry: str, prefix: str | None) -> str | None`, `skill_name(entry: str) -> str`, and `async resolve_skills(settings, *, probe=probe_endpoint, hostname=None) -> list[tuple[str, str]]` returning `(name, url)` pairs for reachable skills only. `probe_endpoint(url)` connects an `MCPToolset(url)` context with bounded retries.

- [ ] **Step 1: Write the failing test**

`tests/test_skills.py`:

```python
from concierge.config import Settings
from concierge.skills import (
    repo_prefix,
    resolve_skills,
    skill_endpoint,
    skill_name,
)


def test_repo_prefix_derivation() -> None:
    assert repo_prefix("local-ha-mcp-concierge-dev") == "local"
    assert repo_prefix("local-ha-mcp-concierge") == "local"
    assert repo_prefix("a1b2c3d4-ha-mcp-concierge") == "a1b2c3d4"
    assert repo_prefix("something-else") is None


def test_skill_endpoint_from_slug() -> None:
    assert (
        skill_endpoint("pixoo", "local")
        == "http://local-ha-concierge-skill-pixoo:9000/mcp"
    )
    assert skill_endpoint("pixoo", None) is None
    assert skill_endpoint("", "local") is None


def test_full_url_passthrough() -> None:
    url = "http://elsewhere:9000/mcp"
    assert skill_endpoint(url, None) == url


def test_skill_name() -> None:
    assert skill_name("pixoo-max") == "pixoo_max"
    assert skill_name("http://divoom-thing:9000/mcp") == "divoom_thing"


async def test_resolve_skills_skips_unreachable() -> None:
    async def probe(url: str) -> bool:
        return "good" in url

    s = Settings(skills=["good", "bad", "http://good-remote:9000/mcp"])
    pairs = await resolve_skills(s, probe=probe, hostname="local-ha-mcp-concierge-dev")
    assert pairs == [
        ("good", "http://local-ha-concierge-skill-good:9000/mcp"),
        ("good_remote", "http://good-remote:9000/mcp"),
    ]


async def test_resolve_skills_no_prefix_skips_bare_slugs() -> None:
    async def probe(url: str) -> bool:
        return True

    s = Settings(skills=["pixoo"])
    assert await resolve_skills(s, probe=probe, hostname="weird-host") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_skills.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'concierge.skills'`.

- [ ] **Step 3: Implement `concierge/skills.py`**

```python
"""Resolve skill add-on slugs to MCP endpoints via Supervisor DNS.

A skill is a sibling add-on named `ha-concierge-skill-<slug>` running a
FastMCP streamable-HTTP server on :9000/mcp. Supervisor DNS names add-ons
`<repo-prefix>-<slug-with-dashes>`; we derive the prefix from our own
hostname, so no Supervisor API privilege is needed. A full http(s) URL entry
is used verbatim (cross-repo escape hatch). Unreachable skills are probed
with bounded retries and skipped so one bad skill never sinks the rest.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable

from pydantic_ai.mcp import MCPToolset

from concierge.config import Settings

logger = logging.getLogger(__name__)

SKILL_PORT = 9000
_SKILL_INFIX = "ha-concierge-skill-"
# Both flavors, dev first so the longer suffix wins.
_OWN_SUFFIXES = ("-ha-mcp-concierge-dev", "-ha-mcp-concierge")
_PROBE_ATTEMPTS = 3
_PROBE_DELAY_SECONDS = 1.5


def repo_prefix(hostname: str) -> str | None:
    for suffix in _OWN_SUFFIXES:
        if hostname.endswith(suffix):
            return hostname[: -len(suffix)] or None
    return None


def _is_url(entry: str) -> bool:
    return entry.startswith(("http://", "https://"))


def skill_endpoint(entry: str, prefix: str | None) -> str | None:
    entry = entry.strip()
    if not entry:
        return None
    if _is_url(entry):
        return entry
    if not prefix:
        return None
    return f"http://{prefix}-{_SKILL_INFIX}{entry}:{SKILL_PORT}/mcp"


def skill_name(entry: str) -> str:
    if _is_url(entry):
        host = entry.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
        return host.replace("-", "_")
    return entry.strip().replace("-", "_")


async def probe_endpoint(url: str) -> bool:
    """Connect (and disconnect) an MCP toolset, retrying briefly."""
    for attempt in range(_PROBE_ATTEMPTS):
        try:
            async with MCPToolset(url):
                return True
        except Exception as exc:  # noqa: BLE001 - degrade per-skill, never crash
            logger.warning(
                "skill endpoint %s unreachable (attempt %d/%d): %s",
                url,
                attempt + 1,
                _PROBE_ATTEMPTS,
                exc,
            )
            if attempt < _PROBE_ATTEMPTS - 1:
                await asyncio.sleep(_PROBE_DELAY_SECONDS)
    return False


async def resolve_skills(
    settings: Settings,
    *,
    probe: Callable[[str], Awaitable[bool]] = probe_endpoint,
    hostname: str | None = None,
) -> list[tuple[str, str]]:
    """Return (name, url) for every configured, reachable skill."""
    prefix = repo_prefix(hostname or socket.gethostname())
    pairs: list[tuple[str, str]] = []
    for entry in settings.skills:
        url = skill_endpoint(entry, prefix)
        if url is None:
            if entry.strip():
                logger.warning(
                    "skill %r cannot be resolved (no repo prefix); "
                    "list it as a full http(s)://.../mcp URL instead",
                    entry,
                )
            continue
        if await probe(url):
            pairs.append((skill_name(entry), url))
    return pairs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_skills.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check . && uv run mypy concierge/
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "feat(concierge): skill endpoint resolution with graceful probing"
```

---

### Task 5: Session store (SQLite)

**Files:**
- Create: `concierge/sessions.py`
- Test: `tests/test_sessions.py`

**Interfaces:**
- Produces: `SessionStore(db_path: Path)` with methods `list_threads() -> list[dict]` (each `{"id", "title", "created_at", "updated_at"}`, newest first), `get_messages(thread_id: str) -> list[dict]`, `replace_messages(thread_id: str, messages: list[dict]) -> None` (upserts the thread row, bumps `updated_at`), `set_title(thread_id, title) -> None`, `rename_thread(thread_id, title) -> bool`, `delete_thread(thread_id) -> bool`, `get_title(thread_id) -> str | None`. Messages are opaque AG-UI dicts stored as JSON.

- [ ] **Step 1: Write the failing test**

`tests/test_sessions.py`:

```python
from pathlib import Path

from concierge.sessions import SessionStore


def make_store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "data" / "concierge.db")  # parent dirs created


def test_replace_and_get_messages_roundtrip(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    msgs = [
        {"id": "u1", "role": "user", "content": "hi"},
        {"id": "a1", "role": "assistant", "content": "hello"},
    ]
    store.replace_messages("t1", msgs)
    assert store.get_messages("t1") == msgs
    assert store.get_messages("missing") == []


def test_replace_overwrites_whole_thread(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.replace_messages("t1", [{"id": "u1", "role": "user", "content": "a"}])
    new = [
        {"id": "u1", "role": "user", "content": "a"},
        {"id": "a1", "role": "assistant", "content": "b"},
    ]
    store.replace_messages("t1", new)
    assert store.get_messages("t1") == new


def test_thread_listing_title_and_delete(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.replace_messages("t1", [{"id": "u1", "role": "user", "content": "x"}])
    store.replace_messages("t2", [{"id": "u2", "role": "user", "content": "y"}])
    threads = store.list_threads()
    assert [t["id"] for t in threads] == ["t2", "t1"]  # newest first
    assert threads[0]["title"] is None

    store.set_title("t1", "Lights")
    assert store.get_title("t1") == "Lights"
    assert store.rename_thread("t1", "Lights!") is True
    assert store.rename_thread("nope", "x") is False

    assert store.delete_thread("t1") is True
    assert store.delete_thread("t1") is False
    assert store.get_messages("t1") == []


def test_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "concierge.db"
    SessionStore(path).replace_messages(
        "t1", [{"id": "u1", "role": "user", "content": "x"}]
    )
    assert SessionStore(path).get_messages("t1") != []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sessions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'concierge.sessions'`.

- [ ] **Step 3: Implement `concierge/sessions.py`**

```python
"""SQLite-backed thread/message store on the add-on /data volume.

Messages are opaque AG-UI message dicts (camelCase wire format) stored as
JSON, one row per message. Writes happen once per turn (replace the thread's
messages at stream end) — deliberate, to keep eMMC churn low. WAL mode keeps
a reader (thread list) from blocking the writer.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    message_json TEXT NOT NULL,
    PRIMARY KEY (thread_id, seq)
);
"""


class SessionStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def list_threads(self) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT id, title, created_at, updated_at FROM threads"
            " ORDER BY updated_at DESC"
        ).fetchall()
        return [
            {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]}
            for r in rows
        ]

    def get_messages(self, thread_id: str) -> list[dict[str, object]]:
        rows = self._conn.execute(
            "SELECT message_json FROM messages WHERE thread_id = ? ORDER BY seq",
            (thread_id,),
        ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def replace_messages(
        self, thread_id: str, messages: list[dict[str, object]]
    ) -> None:
        now = time.time()
        with self._conn:
            self._conn.execute(
                "INSERT INTO threads (id, title, created_at, updated_at)"
                " VALUES (?, NULL, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at",
                (thread_id, now, now),
            )
            self._conn.execute(
                "DELETE FROM messages WHERE thread_id = ?", (thread_id,)
            )
            self._conn.executemany(
                "INSERT INTO messages (thread_id, seq, message_json)"
                " VALUES (?, ?, ?)",
                [
                    (thread_id, seq, json.dumps(message))
                    for seq, message in enumerate(messages)
                ],
            )

    def get_title(self, thread_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT title FROM threads WHERE id = ?", (thread_id,)
        ).fetchone()
        return row[0] if row else None

    def set_title(self, thread_id: str, title: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE threads SET title = ? WHERE id = ?", (title, thread_id)
            )

    def rename_thread(self, thread_id: str, title: str) -> bool:
        with self._conn:
            cur = self._conn.execute(
                "UPDATE threads SET title = ? WHERE id = ?", (title, thread_id)
            )
        return cur.rowcount > 0

    def delete_thread(self, thread_id: str) -> bool:
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM threads WHERE id = ?", (thread_id,)
            )
        return cur.rowcount > 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sessions.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check . && uv run mypy concierge/
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "feat(concierge): SQLite session store"
```

---

### Task 6: AG-UI event accumulator (persistence tee)

**Files:**
- Create: `concierge/stream.py`
- Test: `tests/test_stream.py`

**Interfaces:**
- Consumes: `ag_ui.core` event types (installed by the `ag-ui` extra).
- Produces: `MessageAccumulator(initial_messages: list[dict])` with `feed(event) -> None` and `messages() -> list[dict]`. Accumulates `TEXT_MESSAGE_*` / `TOOL_CALL_*` / `TOOL_CALL_RESULT` events into AG-UI wire-format message dicts appended after `initial_messages` (which come from `RunAgentInput.messages`). Unknown event types are ignored.

- [ ] **Step 1: Write the failing test**

`tests/test_stream.py`:

```python
from ag_ui.core import (
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)

from concierge.stream import MessageAccumulator

USER = {"id": "u1", "role": "user", "content": "turn on the light"}


def test_accumulates_streamed_text() -> None:
    acc = MessageAccumulator([USER])
    acc.feed(TextMessageStartEvent(message_id="a1", role="assistant"))
    acc.feed(TextMessageContentEvent(message_id="a1", delta="Hel"))
    acc.feed(TextMessageContentEvent(message_id="a1", delta="lo"))
    acc.feed(TextMessageEndEvent(message_id="a1"))
    assert acc.messages() == [
        USER,
        {"id": "a1", "role": "assistant", "content": "Hello"},
    ]


def test_accumulates_tool_call_and_result() -> None:
    acc = MessageAccumulator([USER])
    acc.feed(
        ToolCallStartEvent(
            tool_call_id="c1", tool_call_name="ha_call_service", parent_message_id="a1"
        )
    )
    acc.feed(ToolCallArgsEvent(tool_call_id="c1", delta='{"domain":'))
    acc.feed(ToolCallArgsEvent(tool_call_id="c1", delta='"light"}'))
    acc.feed(ToolCallEndEvent(tool_call_id="c1"))
    acc.feed(
        ToolCallResultEvent(
            message_id="r1", tool_call_id="c1", content='{"success": true}'
        )
    )
    assert acc.messages() == [
        USER,
        {
            "id": "a1",
            "role": "assistant",
            "content": "",
            "toolCalls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "ha_call_service",
                        "arguments": '{"domain":"light"}',
                    },
                }
            ],
        },
        {
            "id": "r1",
            "role": "tool",
            "toolCallId": "c1",
            "content": '{"success": true}',
        },
    ]


def test_unknown_events_ignored() -> None:
    class Other:
        type = "RUN_STARTED"

    acc = MessageAccumulator([])
    acc.feed(Other())
    assert acc.messages() == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stream.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'concierge.stream'`.
Note: if the `ag_ui.core` event imports themselves fail, print the module's actual names (`uv run python -c "import ag_ui.core as c; print([n for n in dir(c) if 'Event' in n])"`) and adjust the imports in the test — the event *classes* are part of `ag-ui-protocol` 0.1.19.

- [ ] **Step 3: Implement `concierge/stream.py`**

```python
"""Accumulate a run's AG-UI events into AG-UI wire-format messages.

AG-UI is client-owns-messages: RunAgentInput carries the prior thread. This
tee reconstructs the new assistant/tool messages from the streamed events so
the server can persist the full thread once at stream end. Dict keys use the
protocol's camelCase so stored messages round-trip through RunAgentInput
unchanged.
"""

from __future__ import annotations

from typing import Any

_TEXT_START = "TEXT_MESSAGE_START"
_TEXT_CONTENT = "TEXT_MESSAGE_CONTENT"
_TOOL_START = "TOOL_CALL_START"
_TOOL_ARGS = "TOOL_CALL_ARGS"
_TOOL_RESULT = "TOOL_CALL_RESULT"


def _event_type(event: Any) -> str:
    raw = getattr(event, "type", "")
    return getattr(raw, "value", raw) or ""


class MessageAccumulator:
    def __init__(self, initial_messages: list[dict[str, Any]]) -> None:
        self._messages: list[dict[str, Any]] = list(initial_messages)
        self._by_id: dict[str, dict[str, Any]] = {
            str(m["id"]): m for m in self._messages if "id" in m
        }
        self._tool_calls: dict[str, dict[str, Any]] = {}

    def _message(self, message_id: str, role: str) -> dict[str, Any]:
        message = self._by_id.get(message_id)
        if message is None:
            message = {"id": message_id, "role": role, "content": ""}
            self._messages.append(message)
            self._by_id[message_id] = message
        return message

    def feed(self, event: Any) -> None:
        kind = _event_type(event)
        if kind == _TEXT_START:
            self._message(event.message_id, getattr(event, "role", "assistant"))
        elif kind == _TEXT_CONTENT:
            message = self._message(event.message_id, "assistant")
            message["content"] = str(message.get("content") or "") + event.delta
        elif kind == _TOOL_START:
            parent_id = getattr(event, "parent_message_id", None) or event.tool_call_id
            message = self._message(parent_id, "assistant")
            call = {
                "id": event.tool_call_id,
                "type": "function",
                "function": {"name": event.tool_call_name, "arguments": ""},
            }
            message.setdefault("toolCalls", []).append(call)
            self._tool_calls[event.tool_call_id] = call
        elif kind == _TOOL_ARGS:
            call = self._tool_calls.get(event.tool_call_id)
            if call is not None:
                call["function"]["arguments"] += event.delta
        elif kind == _TOOL_RESULT:
            self._messages.append(
                {
                    "id": event.message_id,
                    "role": "tool",
                    "toolCallId": event.tool_call_id,
                    "content": event.content,
                }
            )

    def messages(self) -> list[dict[str, Any]]:
        return self._messages
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stream.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check . && uv run mypy concierge/
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "feat(concierge): AG-UI event accumulator for turn persistence"
```

---

### Task 7: Agent assembly over MCP toolsets

**Files:**
- Create: `concierge/agent.py`
- Create: `tests/stub_mcp_server.py` (test fixture MCP server)
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `Settings`, `build_model` (Task 2), `approval_callback` (Task 3), `resolve_skills` (Task 4).
- Produces: `SYSTEM_PROMPT: str`; `build_hamcp_toolset(settings) -> AbstractToolset` (stdio ha-mcp, approval-gated unless `auto_run_tools`, NOT prefixed); `build_skill_toolset(name, url, settings) -> AbstractToolset` (HTTP, approval-gated, `.prefixed(name)`); `async build_agent(settings, *, toolsets=None) -> Agent` with `output_type=[str, DeferredToolRequests]` (when `toolsets` is passed, skill/ha-mcp discovery is skipped — the test seam).

- [ ] **Step 1: Write the stub MCP server fixture**

`tests/stub_mcp_server.py`:

```python
"""Minimal annotated MCP server run over stdio in agent tests."""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

mcp = FastMCP("stub")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def get_temperature(room: str) -> str:
    """Get a room's temperature."""
    return f"{room}: 21C"


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def delete_everything(target: str) -> str:
    """Destructively delete a target."""
    return f"deleted {target}"


if __name__ == "__main__":
    mcp.run()
```

- [ ] **Step 2: Write the failing test**

`tests/test_agent.py`:

```python
import sys
from pathlib import Path

from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel

from concierge.agent import SYSTEM_PROMPT, build_agent
from concierge.config import Settings
from concierge.gating import approval_callback

STUB = str(Path(__file__).parent / "stub_mcp_server.py")


def stub_toolset() -> MCPToolset:
    return MCPToolset(StdioTransport(command=sys.executable, args=[STUB]))


async def test_read_only_tool_runs_without_approval() -> None:
    toolset = stub_toolset().approval_required(approval_callback)
    agent = await build_agent(Settings(), toolsets=[toolset])
    result = await agent.run(
        "What is the temperature in the kitchen?",
        model=TestModel(call_tools=["get_temperature"]),
    )
    # ran to completion: plain text output, no interrupt
    assert isinstance(result.output, str)


async def test_destructive_tool_pauses_then_resumes() -> None:
    toolset = stub_toolset().approval_required(approval_callback)
    agent = await build_agent(Settings(), toolsets=[toolset])
    model = TestModel(call_tools=["delete_everything"])

    result = await agent.run("Delete everything in the basement", model=model)
    assert isinstance(result.output, DeferredToolRequests)
    [call] = result.output.approvals
    assert call.tool_name == "delete_everything"

    results = DeferredToolResults()
    results.approvals[call.tool_call_id] = True
    resumed = await agent.run(
        model=model,
        message_history=result.all_messages(),
        deferred_tool_results=results,
    )
    assert isinstance(resumed.output, str)


async def test_auto_run_tools_skips_gating() -> None:
    settings = Settings(auto_run_tools=True)
    # build_agent must NOT wrap in approval_required when auto_run_tools is on;
    # here we hand it the raw toolset and assert the run completes ungated.
    agent = await build_agent(settings, toolsets=[stub_toolset()])
    result = await agent.run(
        "Delete everything",
        model=TestModel(call_tools=["delete_everything"]),
    )
    assert isinstance(result.output, str)


async def test_system_prompt_carries_discovery_policy() -> None:
    agent = await build_agent(Settings(), toolsets=[stub_toolset()])
    assert isinstance(agent, Agent)
    assert "search" in SYSTEM_PROMPT.lower()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_agent.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'concierge.agent'`.

- [ ] **Step 4: Implement `concierge/agent.py`**

```python
"""Assemble the Concierge agent: model + MCP toolsets + approval gating."""

from __future__ import annotations

import os

from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import AbstractToolset

from concierge.config import Settings
from concierge.gating import approval_callback
from concierge.models import build_model
from concierge.skills import resolve_skills

SYSTEM_PROMPT = """\
You are Concierge, a helpful assistant for this Home Assistant home.

You control and inspect the home exclusively through your tools. When the
user mentions a device, area, or automation you do not have an exact id for,
first resolve it with whatever search/list/lookup tools are available (prefer
fuzzy or partial matching); only ask the user when no tool can resolve it.
Confirm what you did after acting. Be concise.
"""


def _gated(toolset: MCPToolset, settings: Settings) -> AbstractToolset:
    if settings.auto_run_tools:
        return toolset
    return toolset.approval_required(approval_callback)


def build_hamcp_toolset(settings: Settings) -> AbstractToolset:
    """Bundled ha-mcp over stdio. Tools already carry ha_* names: no prefix."""
    env = {
        **os.environ,
        "HOMEASSISTANT_URL": settings.ha_url,
        "HOMEASSISTANT_TOKEN": settings.ha_token,
    }
    transport = StdioTransport(command="ha-mcp", args=[], env=env)
    return _gated(MCPToolset(transport), settings)


def build_skill_toolset(
    name: str, url: str, settings: Settings
) -> AbstractToolset:
    """One skill add-on over streamable HTTP, gated then namespaced."""
    return _gated(MCPToolset(url), settings).prefixed(name)


async def build_agent(
    settings: Settings,
    *,
    toolsets: list[AbstractToolset] | None = None,
) -> Agent:
    """Build the agent; pass `toolsets` explicitly to skip discovery (tests)."""
    if toolsets is None:
        toolsets = [build_hamcp_toolset(settings)]
        for name, url in await resolve_skills(settings):
            toolsets.append(build_skill_toolset(name, url, settings))
    return Agent(
        build_model(settings),
        instructions=SYSTEM_PROMPT,
        toolsets=toolsets,
        output_type=[str, DeferredToolRequests],
    )
```

Note: if `pydantic_ai.toolsets.AbstractToolset` is not the exported name, check with `uv run python -c "import pydantic_ai.toolsets as t; print([n for n in dir(t) if 'Toolset' in n])"` and use the abstract base it prints — only the annotation changes.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_agent.py -v`
Expected: 4 PASS. (These spawn stdio subprocesses; allow a few seconds.)

- [ ] **Step 6: Lint, type-check, commit**

```bash
uv run ruff check . && uv run mypy concierge/
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "feat(concierge): agent assembly with gated MCP toolsets"
```

---

### Task 8: Title generation

**Files:**
- Create: `concierge/title.py`
- Test: `tests/test_title.py`

**Interfaces:**
- Consumes: `build_title_model` (Task 2).
- Produces: `async generate_title(settings: Settings, user_text: str, *, model=None) -> str` — one cheap model call, returns a ≤60-char single-line title (`model=` overrides for tests).

- [ ] **Step 1: Write the failing test**

`tests/test_title.py`:

```python
from pydantic_ai.models.test import TestModel

from concierge.config import Settings
from concierge.title import generate_title


async def test_generates_short_single_line_title() -> None:
    model = TestModel(custom_output_text="Kitchen lights \n schedule question")
    title = await generate_title(Settings(), "how do I schedule my lights?", model=model)
    assert title == "Kitchen lights schedule question"
    assert "\n" not in title


async def test_truncates_to_60_chars() -> None:
    model = TestModel(custom_output_text="x" * 200)
    title = await generate_title(Settings(), "hello", model=model)
    assert len(title) <= 60
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_title.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'concierge.title'`.

- [ ] **Step 3: Implement `concierge/title.py`**

```python
"""Generate a short thread title from the first user message."""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models import Model

from concierge.config import Settings
from concierge.models import build_title_model

_MAX_LEN = 60
_INSTRUCTIONS = (
    "Write a title (at most 6 words) for a conversation that starts with the"
    " given message. Reply with the title only - no quotes, no punctuation at"
    " the end."
)


async def generate_title(
    settings: Settings, user_text: str, *, model: Model | str | None = None
) -> str:
    agent: Agent = Agent(
        model or build_title_model(settings),
        instructions=_INSTRUCTIONS,
        output_type=str,
    )
    result = await agent.run(user_text)
    return " ".join(result.output.split())[:_MAX_LEN].strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_title.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check . && uv run mypy concierge/
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "feat(concierge): auto-title generation"
```

---

### Task 9: FastAPI app — AG-UI endpoint with persistence tee + thread CRUD

**Files:**
- Create: `concierge/web.py`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `AGUIAdapter` (`pydantic_ai.ui.ag_ui`), `SSE_CONTENT_TYPE` (`pydantic_ai.ui`), `MessageAccumulator` (Task 6), `SessionStore` (Task 5), `build_agent` (Task 7), `generate_title` (Task 8).
- Produces: `create_app(settings, *, agent, store, title_fn=generate_title) -> FastAPI` with routes `POST /agui`, `GET /threads`, `GET /threads/{id}`, `PATCH /threads/{id}`, `DELETE /threads/{id}`. (SPA static serving is added in Plan 2 when a built frontend exists.) `agent`/`store`/`title_fn` are injected — production wiring happens in Task 12.

- [ ] **Step 1: Write the failing test**

`tests/test_web.py`:

```python
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel

from concierge.agent import build_agent
from concierge.config import Settings
from concierge.gating import approval_callback
from concierge.sessions import SessionStore
from concierge.web import create_app

STUB = str(Path(__file__).parent / "stub_mcp_server.py")


def run_input(thread_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "runId": str(uuid.uuid4()),
        "messages": messages,
        "tools": [],
        "context": [],
        "state": None,
        "forwardedProps": None,
    }


def sse_events(body: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


@pytest.fixture
async def client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    toolset = MCPToolset(
        StdioTransport(command=sys.executable, args=[STUB])
    ).approval_required(approval_callback)
    agent = await build_agent(settings, toolsets=[toolset])
    store = SessionStore(tmp_path / "concierge.db")

    async def fake_title(settings: Settings, user_text: str, **kwargs: Any) -> str:
        return "Test title"

    app = create_app(settings, agent=agent, store=store, title_fn=fake_title)
    # TestModel: answer directly without calling tools.
    app.state.model_override = TestModel(call_tools=[])
    with TestClient(app) as c:
        yield c, store


async def test_agui_run_streams_and_persists(client) -> None:
    c, store = client
    tid = "t-" + uuid.uuid4().hex[:8]
    user = {"id": "u1", "role": "user", "content": "hello"}
    resp = c.post("/agui", json=run_input(tid, [user]))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    types = [e["type"] for e in sse_events(resp.text)]
    assert types[0] == "RUN_STARTED"
    assert types[-1] == "RUN_FINISHED"

    # persisted: user message + at least one assistant message
    stored = store.get_messages(tid)
    assert stored[0] == user
    assert any(m.get("role") == "assistant" for m in stored)
    # title generated for the new thread
    assert store.get_title(tid) == "Test title"


async def test_thread_crud(client) -> None:
    c, store = client
    store.replace_messages("t9", [{"id": "u1", "role": "user", "content": "x"}])

    listed = c.get("/threads").json()
    assert [t["id"] for t in listed] == ["t9"]

    assert c.get("/threads/t9").json() == [
        {"id": "u1", "role": "user", "content": "x"}
    ]
    assert c.get("/threads/missing").status_code == 404

    assert c.patch("/threads/t9", json={"title": "Renamed"}).status_code == 200
    assert store.get_title("t9") == "Renamed"
    assert c.patch("/threads/no", json={"title": "x"}).status_code == 404

    assert c.delete("/threads/t9").status_code == 204
    assert c.delete("/threads/t9").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_web.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'concierge.web'`.

- [ ] **Step 3: Implement `concierge/web.py`**

```python
"""FastAPI app: the AG-UI run endpoint plus the thread REST surface.

POST /agui uses Pydantic AI's AGUIAdapter (manual form: build_run_input ->
run_stream -> encode_stream) with a tee that accumulates the run's events
and persists the whole thread once at stream end. AG-UI is
client-owns-messages, so RunAgentInput.messages is the run's context; the
store exists for cross-session rehydration via GET /threads/{id}.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent
from pydantic_ai.ui import SSE_CONTENT_TYPE
from pydantic_ai.ui.ag_ui import AGUIAdapter

from concierge.config import Settings
from concierge.sessions import SessionStore
from concierge.stream import MessageAccumulator
from concierge.title import generate_title

logger = logging.getLogger(__name__)

TitleFn = Callable[..., Awaitable[str]]


class RenameBody(BaseModel):
    title: str


def _first_user_text(messages: list[dict[str, Any]]) -> str:
    for message in messages:
        if message.get("role") == "user" and message.get("content"):
            return str(message["content"])
    return ""


def create_app(
    settings: Settings,
    *,
    agent: Agent,
    store: SessionStore,
    title_fn: TitleFn = generate_title,
) -> FastAPI:
    app = FastAPI(title="concierge")

    async def _maybe_title(thread_id: str, messages: list[dict[str, Any]]) -> None:
        if store.get_title(thread_id) is not None:
            return
        user_text = _first_user_text(messages)
        if not user_text:
            return
        try:
            store.set_title(thread_id, await title_fn(settings, user_text))
        except Exception:  # noqa: BLE001 - titling must never break a turn
            logger.exception("title generation failed for thread %s", thread_id)

    @app.post("/agui")
    async def run_agui(request: Request) -> Response:
        try:
            run_input = AGUIAdapter.build_run_input(await request.body())
        except ValidationError as exc:
            return JSONResponse(
                json.loads(exc.json()),
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            )
        accept = request.headers.get("accept", SSE_CONTENT_TYPE)
        adapter = AGUIAdapter(agent=agent, run_input=run_input, accept=accept)

        initial = [
            m.model_dump(by_alias=True, exclude_none=True)
            for m in run_input.messages
        ]
        accumulator = MessageAccumulator(initial)

        run_kwargs: dict[str, Any] = {}
        model_override = getattr(app.state, "model_override", None)
        if model_override is not None:  # test seam; production never sets it
            run_kwargs["model"] = model_override

        async def teed() -> AsyncIterator[Any]:
            try:
                async for event in adapter.run_stream(**run_kwargs):
                    accumulator.feed(event)
                    yield event
            finally:
                store.replace_messages(run_input.thread_id, accumulator.messages())
                await _maybe_title(run_input.thread_id, accumulator.messages())

        return StreamingResponse(adapter.encode_stream(teed()), media_type=accept)

    @app.get("/threads")
    async def list_threads() -> list[dict[str, Any]]:
        return await asyncio.to_thread(store.list_threads)

    @app.get("/threads/{thread_id}")
    async def get_thread(thread_id: str) -> Response:
        messages = await asyncio.to_thread(store.get_messages, thread_id)
        if not messages:
            return JSONResponse({"error": "thread not found"}, status_code=404)
        return JSONResponse(messages)

    @app.patch("/threads/{thread_id}")
    async def rename_thread(thread_id: str, body: RenameBody) -> Response:
        renamed = await asyncio.to_thread(store.rename_thread, thread_id, body.title)
        if not renamed:
            return JSONResponse({"error": "thread not found"}, status_code=404)
        return JSONResponse({"id": thread_id, "title": body.title})

    @app.delete("/threads/{thread_id}")
    async def delete_thread(thread_id: str) -> Response:
        deleted = await asyncio.to_thread(store.delete_thread, thread_id)
        if not deleted:
            return JSONResponse({"error": "thread not found"}, status_code=404)
        return Response(status_code=204)

    return app
```

Note on `run_stream(model=...)`: the test injects `TestModel` via `app.state.model_override`. If `AGUIAdapter.run_stream()` does not accept a `model=` kwarg (check: `uv run python -c "import inspect; from pydantic_ai.ui.ag_ui import AGUIAdapter; print(inspect.signature(AGUIAdapter.run_stream))"`), pass the override at agent level instead: in the test fixture, build the agent with `Agent(TestModel(call_tools=[]), ...)` semantics by giving `build_agent` a `Settings` object then calling `agent.override(model=TestModel(call_tools=[]))` as a context manager around the request, and call `adapter.run_stream()` with no kwargs. Prefer whichever form the signature supports; assertions stay identical.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_web.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Lint, type-check, commit**

```bash
uv run ruff check . && uv run mypy concierge/
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "feat(concierge): AG-UI endpoint with persistence tee and thread CRUD"
```

---

### Task 10: HITL over the wire — interrupt/resume integration test

**Files:**
- Test: `tests/test_hitl_flow.py`

**Interfaces:**
- Consumes: everything above; no new production code expected (this task *proves* the §5.5 flow through the HTTP layer; small fixes to `web.py`/`stream.py` are in scope if the test exposes gaps).

- [ ] **Step 1: Discover the exact interrupt/resume field names**

The AG-UI resume shape is the one contract we could not fully pin from docs. Print the models once and use what they say:

Run: `uv run python -c "from ag_ui.core import RunAgentInput; print(RunAgentInput.model_fields.keys())"`
Run: `uv run python -c "import ag_ui.core as c; print([n for n in dir(c) if 'esume' in n or 'nterrupt' in n])"; uv run python -c "from ag_ui.core import ResumeEntry; print(ResumeEntry.model_fields)" 2>/dev/null || true`
Expected: field names for the resume array on `RunAgentInput` (e.g. `resume`) and the entry shape (id + payload). Substitute the printed names for `resume` / `id` / `payload` below if they differ.

- [ ] **Step 2: Write the failing test**

`tests/test_hitl_flow.py`:

```python
import json
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.test import TestModel

from concierge.agent import build_agent
from concierge.config import Settings
from concierge.gating import approval_callback
from concierge.sessions import SessionStore
from concierge.web import create_app

STUB = str(Path(__file__).parent / "stub_mcp_server.py")


def sse_events(body: str) -> list[dict[str, Any]]:
    return [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]


def base_input(thread_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "threadId": thread_id,
        "runId": str(uuid.uuid4()),
        "messages": messages,
        "tools": [],
        "context": [],
        "state": None,
        "forwardedProps": None,
    }


@pytest.fixture
async def client(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    toolset = MCPToolset(
        StdioTransport(command=sys.executable, args=[STUB])
    ).approval_required(approval_callback)
    agent = await build_agent(settings, toolsets=[toolset])
    store = SessionStore(tmp_path / "concierge.db")

    async def fake_title(settings: Settings, user_text: str, **kw: Any) -> str:
        return "t"

    app = create_app(settings, agent=agent, store=store, title_fn=fake_title)
    app.state.model_override = TestModel(call_tools=["delete_everything"])
    with TestClient(app) as c:
        yield c, store


async def test_destructive_tool_interrupts_then_resumes(client) -> None:
    c, store = client
    tid = "t-" + uuid.uuid4().hex[:8]
    user = {"id": "u1", "role": "user", "content": "delete everything downstairs"}

    # Turn 1: gated tool -> RUN_FINISHED carries an interrupt outcome.
    first = c.post("/agui", json=base_input(tid, [user]))
    events = sse_events(first.text)
    finished = [e for e in events if e["type"] == "RUN_FINISHED"][-1]
    outcome = finished.get("outcome") or {}
    assert outcome.get("type") == "interrupt"
    interrupts = outcome["interrupts"]
    assert len(interrupts) == 1

    # Turn 2: resume with approval; stream must contain the tool result.
    stored = store.get_messages(tid)
    resume_input = base_input(tid, stored)
    resume_input["resume"] = [
        {"id": interrupts[0]["id"], "payload": {"approved": True}}
    ]
    second = c.post("/agui", json=resume_input)
    types = [e["type"] for e in sse_events(second.text)]
    assert "TOOL_CALL_RESULT" in types
    final = [e for e in sse_events(second.text) if e["type"] == "RUN_FINISHED"][-1]
    assert (final.get("outcome") or {}).get("type") != "interrupt"
```

- [ ] **Step 3: Run test — iterate on field names only**

Run: `uv run pytest tests/test_hitl_flow.py -v`
Expected: PASS. If it fails on a missing/renamed field (`resume`, `id`, `payload`, `outcome`, `interrupts`), correct the test to the names printed in Step 1 / the actual `RUN_FINISHED` payload (print `events` on failure) — do NOT change the production gating logic to make it pass. If the *persisted* messages turn out to be insufficient for the adapter to reconstruct the pending call on resume (assertion on turn 2 fails), the fix belongs in `MessageAccumulator` (persist whatever message parts the interrupt round-trip needs) — that is in scope for this task.

- [ ] **Step 4: Commit**

```bash
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "test(concierge): HITL interrupt/resume over the AG-UI wire"
```

---

### Task 11: Live ha-mcp wiring test (annotation casing + stdio launch)

**Files:**
- Test: `tests/test_hamcp_wiring.py`

**Interfaces:**
- Consumes: `build_hamcp_toolset` (Task 7). ha-mcp 7.12.0 is already an install dependency, so its `ha-mcp` console script exists in this venv.

- [ ] **Step 1: Write the test**

`tests/test_hamcp_wiring.py`:

```python
"""Wire the real bundled ha-mcp over stdio and lock the annotation contract.

Uses a fake HOMEASSISTANT_URL: listing tools must not require a live HA.
This is the one live check the design flagged (spec §5.5/§11.3): the exact
key casing of MCP annotations as surfaced to our gating callback.
"""

from concierge.agent import build_hamcp_toolset
from concierge.config import Settings


def settings() -> Settings:
    return Settings(
        ha_url="http://127.0.0.1:1", ha_token="fake-token", auto_run_tools=True
    )


async def test_hamcp_lists_tools_with_camel_case_annotations() -> None:
    # auto_run_tools=True -> raw MCPToolset (no approval wrapper), so we can
    # use the toolset's own client surface directly.
    toolset = build_hamcp_toolset(settings())
    async with toolset:
        tools = await toolset.list_tools()
    by_name = {t.name: t for t in tools}
    assert "ha_search" in by_name  # a stable, core ha-mcp tool

    annotated = [t for t in tools if t.annotations is not None]
    assert annotated, "expected ha-mcp to expose MCP annotations"
    # the exact casing our gating reads: camelCase hints
    sample = annotated[0].annotations
    assert hasattr(sample, "readOnlyHint") and hasattr(sample, "destructiveHint")
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_hamcp_wiring.py -v` (first run downloads nothing; ha-mcp starts as a subprocess — allow ~15s)
Expected: PASS. If `list_tools` is not a method on the toolset, discover the client surface with `uv run python -c "from pydantic_ai.mcp import MCPToolset; print([m for m in dir(MCPToolset) if 'tool' in m.lower() or 'list' in m.lower()])"` and use the listed method (the resources example in the docs shows `list_resources()`, so a sibling tools accessor exists). If ha-mcp's stdio startup does require a reachable HA even for tools/list, replace the fake URL with the note `pytest.skip("needs live HA - covered by Plan 3 e2e")` **and record that finding in the plan-3 notes** — do not delete the test.

- [ ] **Step 3: Commit**

```bash
cd ../.. && git add homeassistant-addon-concierge-dev/backend && git commit -m "test(concierge): live ha-mcp stdio wiring locks annotation casing"
```

---

### Task 12: Entrypoint + repo tooling wiring + smoke run

**Files:**
- Create: `concierge/__main__.py`
- Modify: `lefthook.yml` (repo root of the worktree) — add a concierge mypy job next to `mypy-webhook-proxy`
- Test: `tests/test_entrypoint.py`

**Interfaces:**
- Consumes: `create_app`, `build_agent`, `SessionStore`, `load_settings`.
- Produces: `python -m concierge` serving the app; `make_production_app() -> FastAPI` (the composition root used by `__main__` and, later, the Docker CMD).

- [ ] **Step 1: Write the failing test**

`tests/test_entrypoint.py`:

```python
from concierge.__main__ import make_production_app


async def test_make_production_app_builds(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CONCIERGE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONCIERGE_HA_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("CONCIERGE_HA_TOKEN", "fake")
    app = await make_production_app()
    routes = {r.path for r in app.routes}
    assert {"/agui", "/threads", "/threads/{thread_id}"} <= routes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_entrypoint.py -v`
Expected: FAIL with `ModuleNotFoundError` (no `concierge.__main__`).

- [ ] **Step 3: Implement `concierge/__main__.py`**

```python
"""Entrypoint: build the production app and serve it with uvicorn."""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from fastapi import FastAPI
from pydantic_ai import Agent

from concierge.agent import build_agent
from concierge.config import load_settings
from concierge.sessions import SessionStore
from concierge.web import create_app


async def make_production_app() -> FastAPI:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level.upper())
    if settings.tracing:
        # OTel spans for every run; the operator points the standard
        # OTEL_EXPORTER_OTLP_* env vars at Langfuse or Logfire (spec §5.7).
        Agent.instrument_all()
    agent = await build_agent(settings)
    store = SessionStore(settings.data_dir / "concierge.db")
    return create_app(settings, agent=agent, store=store)


def main() -> None:
    settings = load_settings()
    app = asyncio.run(make_production_app())
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_entrypoint.py -v`
Expected: PASS. (Skill discovery runs with `skills=[]` → no probing; ha-mcp toolset is constructed lazily, not connected, so no HA needed.) If `build_agent` in Task 7 eagerly connects and this fails, make discovery lazy: construct toolsets without entering their contexts (Pydantic AI connects per-run) — that adjustment is in scope.

- [ ] **Step 5: Add the lefthook job** (edit repo-root `lefthook.yml`, in the same `jobs:` list that contains `mypy-webhook-proxy`)

```yaml
          - name: mypy-concierge
            glob: "homeassistant-addon-concierge-dev/backend/**/*.py"
            run: uv run --project homeassistant-addon-concierge-dev/backend mypy homeassistant-addon-concierge-dev/backend/concierge/
```

- [ ] **Step 6: Full suite + smoke run**

```bash
uv run pytest -v                       # whole backend suite green
uv run ruff check . && uv run mypy concierge/
```

Smoke (two terminals or backgrounded):

```bash
CONCIERGE_DATA_DIR=/tmp/concierge-smoke CONCIERGE_HA_URL=http://127.0.0.1:1 \
CONCIERGE_HA_TOKEN=fake CONCIERGE_API_KEY=dummy uv run python -m concierge &
sleep 3
curl -s localhost:8098/threads          # expect: []
curl -sN -X POST localhost:8098/agui -H 'content-type: application/json' \
  -d '{"threadId":"smoke1","runId":"r1","messages":[{"id":"u1","role":"user","content":"hi"}],"tools":[],"context":[],"state":null,"forwardedProps":null}' | head -5
# expect: SSE lines starting with RUN_STARTED, then RUN_ERROR (dummy API key
# cannot reach a real model) - the transport works end-to-end.
kill %1
```

- [ ] **Step 7: Commit**

```bash
cd ../.. && git add homeassistant-addon-concierge-dev/backend lefthook.yml
git commit -m "feat(concierge): entrypoint, composition root, and repo lint wiring"
```

---

## Definition of done (Plan 1)

- `uv run pytest -v` green in `homeassistant-addon-concierge-dev/backend/` (12 test files).
- `uv run ruff check .` and `uv run mypy concierge/` clean.
- Smoke run shows an AG-UI SSE stream over `POST /agui` and working `/threads` CRUD.
- All commits on `feat/concierge-addon`; nothing touches master.
- Findings that affect later plans (resume field names from Task 10, any Task 11 skip) recorded in `docs/superpowers/notes/` for Plan 2/3.
