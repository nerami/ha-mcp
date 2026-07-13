# Concierge Add-on — Tooling Verification (no-assumptions)

- **Date:** 2026-07-09
- **Purpose:** Verify every technical assumption in
  `docs/superpowers/specs/2026-07-09-concierge-addon-design.md` against the
  **latest** versions of each tool, with version + source for each claim.
- **Method:** Pydantic AI docs via Context7 (mirrors `github.com/pydantic/pydantic-ai`
  `main`), the released docs at `pydantic.dev/docs/ai`, PyPI/npm registries, and
  the live `ha-mcp` source in this repo (`src/ha_mcp/`, v7.12.0).

## Recommended pins (bottom line)

| Package | Pin | Latest as of 2026-07-09 | Source |
|---|---|---|---|
| `pydantic-ai` / `pydantic-ai-slim[ag-ui,mcp]` | **2.8.0** | 2.8.0 | https://pypi.org/pypi/pydantic-ai/json , https://pypi.org/pypi/pydantic-ai-slim/json |
| `ha-mcp` (PyPI) | **7.12.0** | 7.12.0 | https://pypi.org/pypi/ha-mcp/json (local repo also 7.12.0) |
| `ag-ui-protocol` (Python, `ag_ui.core`) | **>=0.1.10**, latest 0.1.19 | 0.1.19 (2026-06-02) | pulled by `pydantic-ai-slim[ag-ui]`; https://pypi.org/pypi/ag-ui-protocol/json |
| `@ag-ui/client` (npm) | **0.0.57** | 0.0.57 | https://registry.npmjs.org/@ag-ui/client/latest |

Pydantic AI requires Python **>=3.10**; ha-mcp is **3.13-only** — compatible.

---

## 1. MCP-tool approval gating — THE unproven seam

**Verdict: CONFIRMED — cleanly supported, and better than the spec's hand-wavy "small toolset wrapper".**

Pydantic AI ships a first-class toolset combinator for exactly this. Every
toolset (including an `MCPToolset`) has `.approval_required(func)`:

```python
approval_gated = mcp_toolset.approval_required(
    lambda ctx, tool_def, tool_args: _is_destructive(tool_def)
)
```

`func(ctx, tool_def, tool_args) -> bool` is called per proposed call. Returning
`True` routes the call into the run's `DeferredToolRequests.approvals` instead of
executing it — the *same* machinery `requires_approval=True` uses on local
tools, so it drives the AG-UI interrupt lifecycle identically. If `func` is
omitted, *all* calls require approval.

- **Source (toolsets):** https://github.com/pydantic/pydantic-ai/blob/main/docs/toolsets.md — "`ApprovalRequiredToolset` wraps a toolset to dynamically require approval… passed the run context, the tool's definition, and the validated tool call arguments."
- **Source (deferred/HITL):** https://github.com/pydantic/pydantic-ai/blob/main/docs/deferred-tools.md
- **Version:** pydantic-ai 2.8.0.

We do **not** need to write a custom wrapper. We do not need the per-function
`requires_approval=` decorator (that only exists on locally-declared
`@agent.tool` / `@agent.tool_plain`). `.approval_required()` is the MCP-tool path.

**Related combinators available on the same toolset object** (all documented,
2.8.0): `.filtered(lambda ctx, tool_def: ...)` (drop tools), `.prepared(fn)`
(rewrite tool defs), `.prefixed('name')` (name-prefix). Source:
https://github.com/pydantic/pydantic-ai/blob/main/docs/toolsets.md

**Resume mechanism** (server side): the next run passes
`deferred_tool_results=DeferredToolResults(approvals={tool_call_id: True | ToolDenied('...') | ToolApproved(...)})`
plus `message_history`. Source: deferred-tools.md (worked example).

---

## 2. MCP annotations exposure (gate by `destructiveHint`/`readOnlyHint`)

**Verdict: CONFIRMED — annotations are surfaced on the `ToolDefinition`, and ha-mcp sets them.**

Pydantic AI's MCP client copies MCP tool `annotations` onto the tool definition:

> "The `metadata` dictionary on the `ToolDefinition` object contains `meta` and
> `annotations` fields, along with the tool's output schema in the
> `return_schema` field." — https://github.com/pydantic/pydantic-ai/blob/main/docs/mcp/client.md (2.8.0)

So inside the `.approval_required` callback we read:

```python
def _is_destructive(tool_def) -> bool:
    ann = (tool_def.metadata or {}).get("annotations") or {}
    # read-only -> auto-run; otherwise gate on destructiveHint (MCP default True)
    if ann.get("readOnlyHint"):
        return False
    return ann.get("destructiveHint", True)
```

**ha-mcp actually sets these annotations.** `grep` of `src/ha_mcp/tools/` shows
**92** occurrences of `destructiveHint`/`readOnlyHint`, applied via FastMCP's
`@tool(annotations={...})`. Examples: `tools_todo.py` (`readOnlyHint:True` on
get, `destructiveHint:True` on set), `backup.py`, `tools_registry.py`,
`tools_config_helpers.py`. These flow through FastMCP → MCP `tools/list`
`annotations` → Pydantic AI `ToolDefinition.metadata['annotations']`.

**Caveat to verify at implementation:** confirm the *exact* nested key path at
runtime (`tool_def.metadata['annotations']['destructiveHint']`) with one live
`tools/list` against the bundled server — the docs name the fields but not the
casing after Pydantic AI's ingest. A trivial one-off assertion in a wiring test
(`TestModel` + stub MCP server exposing an annotated tool) locks it down.
**Fallback if a tool lacks annotations:** treat missing/absent as destructive
(fail-safe), plus an optional name allowlist for known read-only tools. ha-mcp
does not annotate 100% of tools, so the fail-safe default matters.

---

## 3. Pydantic AI version + AG-UI adapter import paths/API

**Verdict: CONFIRMED (v2 is stable; pin 2.8.0).**

- Latest stable **2.8.0**, `requires_python >=3.10`. Source: https://pypi.org/pypi/pydantic-ai/json
- Adapter import path: **`from pydantic_ai.ui.ag_ui import AGUIAdapter`**; shared
  symbols **`from pydantic_ai.ui import SSE_CONTENT_TYPE, StateDeps`**. Confirmed
  in the *released* docs: https://pydantic.dev/docs/ai/integrations/ui/ag-ui/
  (import path `pydantic_ai.ui.ag_ui.AGUIAdapter`; install `pydantic-ai-slim[ag-ui]`).
- Methods all confirmed present: `AGUIAdapter.dispatch_request(request, agent=..., deps=...)`
  (one-call Starlette path), and the manual trio
  `build_run_input(await request.body())` → `AGUIAdapter(agent=..., run_input=..., accept=...).run_stream()`
  → `adapter.encode_stream(event_stream)` for custom FastAPI wiring. Source:
  https://github.com/pydantic/pydantic-ai/blob/main/docs/ui/ag-ui.md
- `StateDeps[BaseModel]` for AG-UI shared state confirmed (same source). Note
  `dispatch_request` *mutates* `deps.state` — pass `replace(deps)` per request.
- **v1→v2 differences that bite:** `DeferredToolCalls` was **renamed to
  `DeferredToolRequests`** in v2.0.0 (source: tools.py docstring). The AG-UI
  adapter also moved namespace: v1 exposed `pydantic_ai.ag_ui`; v2 is
  `pydantic_ai.ui.ag_ui`. **Pin 2.8.0 and use the v2 paths.** There is also a
  `VercelAIAdapter` at `pydantic_ai.ui.vercel_ai` (not needed here).

The FastAPI `POST /agui` in the spec maps to the manual `build_run_input →
run_stream → encode_stream` form (returns `StreamingResponse(..., media_type=SSE_CONTENT_TYPE)`).

---

## 4. AG-UI interrupt/resume request/response shape

**Verdict: CONFIRMED.**

- On a gated call the SSE stream ends with **`RUN_FINISHED`** whose
  **`outcome.type == "interrupt"`**; `outcome.interrupts[]` lists each pending
  approval. Adapter maps `Interrupt.reason="tool_call"`, `Interrupt.tool_call_id`
  = the proposed `ToolCallPart.tool_call_id`, `Interrupt.id` derived from it.
- The FE resumes by POSTing the next **`RunAgentInput`** carrying a **`resume[]`**
  array; each `ResumeEntry.payload` is `{ "approved": bool, "editedArgs"?: object,
  "reason"?: string }`. `approved:true → ToolApproved`; `approved:false →
  ToolDenied(payload.reason)`; `editedArgs` replaces the proposed args.
- Source: https://github.com/pydantic/pydantic-ai/blob/main/docs/ui/ag-ui.md
  ("Tool approval (interrupts)") and released
  https://pydantic.dev/docs/ai/integrations/ui/ag-ui/ .
- **Implication for §5.4:** the interrupt/resume round-trip is fully
  client-driven (FE resends `RunAgentInput`+`resume[]`); Pydantic AI reconstructs
  approvals from the message history + resume payload. A server-side
  `pending_approvals` table is **not required**. Keep §5.4's SQLite history
  (needed to rehydrate `message_history`); drop the optional approvals table.

---

## 5. `@ag-ui/client` in a browser without React

**Verdict: WORKS — framework-agnostic — with one caveat (RxJS weight).**

- Latest **0.0.57**. Dependencies: `rxjs@7.8.1`, `zod`, `uuid`,
  `fast-json-patch`, `untruncate-json`, `compare-versions`, `@ag-ui/core`,
  `@ag-ui/encoder`, `@ag-ui/proto`. **No React.** Source:
  https://registry.npmjs.org/@ag-ui/client/latest
- Core class **`HttpAgent`** (extends `AbstractAgent`) POSTs `RunAgentInput` and
  exposes the event stream; consume via `AgentSubscriber` (an RxJS-observable
  event system). Framework-agnostic; React bindings (CopilotKit) are a *separate*
  package. Source: https://docs.ag-ui.com/sdk/js/client/overview
- **Caveat:** `HttpAgent` drags in **RxJS** (+ zod, proto/encoder) — noticeable
  weight for a lean Lit bundle, and an RxJS-observable API to adapt into a Lit
  `ReactiveController`. The spec's alternative — hand-parse the SSE with
  `fetch` + `response.body.getReader()` + `TextDecoder` against the stable AG-UI
  event enum — is fully viable and lighter. **Recommendation:** hand-parse SSE
  for v1 (a few dozen lines, zero deps, exact control of the interrupt handling);
  keep `@ag-ui/client` as a fallback if event coverage gets fiddly. `EventSource`
  is unusable (GET-only) as the spec already notes — correct.

---

## 6. Bundled ha-mcp transport (stdio vs localhost HTTP)

**Verdict: WORKS — recommend stdio via `MCPToolset(StdioTransport(...))`. NOTE the API rename (see §7).**

ha-mcp entrypoints (from `pyproject.toml`): `ha-mcp` (stdio, `__main__:main`),
`ha-mcp-web` (streamable-HTTP, `main_web`), `ha-mcp-sse` (`main_sse`).

- **stdio viability:** `_check_stdin_available()` in `src/ha_mcp/__main__.py`
  explicitly allows **FIFO pipes** (`stat.S_ISFIFO`) and regular files, not just
  TTYs. A subprocess launched by Pydantic AI's stdio transport gets a pipe → OK.
  The scary `_STDIN_ERROR_MESSAGE` only fires for `docker run` **without `-i`**
  (stdin = `/dev/null`, immediate EOF); it does **not** affect a child process
  spawned with a stdin pipe. So stdio-subprocess is safe.
- **HTTP mode needs auth + a port.** `ha-mcp-web` binds a secret URL path
  (`MCP_SECRET_PATH`, default `/mcp`) and enforces a host/origin guard
  (`transport_security.py`). Using localhost-HTTP means managing a port, the
  secret path, and the origin guard inside one container — pure overhead for an
  in-container consumer.
- **Recommendation: stdio.** No port, no secret, no origin guard; ha-mcp's own
  curation/annotations pass through unchanged. Launch it as a subprocess
  (`command="ha-mcp"` with `HOMEASSISTANT_URL`/`HOMEASSISTANT_TOKEN` in env).
  Source: `src/ha_mcp/__main__.py`, `src/ha_mcp/transport_security.py`, repo
  `AGENTS.md` Docker section.

---

## 7. Per-MCP-server tool-name prefixing — **SPEC CORRECTION**

**Verdict: DOES-NOT-work-as-specced (name is stale) — but the capability exists.**

- The spec says "native `tool_prefix`". In Pydantic AI **v2** the documented
  idiom is the **`.prefixed('name')`** method on a toolset:
  `MCPToolset('http://localhost:3001/mcp').prefixed('weather')` → `weather_*`.
  Source: https://github.com/pydantic/pydantic-ai/blob/main/docs/mcp/client.md
- **Bigger correction:** `MCPServerStdio` / `MCPServerStreamableHTTP` (named in
  spec §5.2 and §11) are **DEPRECATED in v2 and will be removed.** The class is
  literally decorated:
  `@deprecated('MCPServerStdio is deprecated and will be removed in v2. Use MCPToolset(...)')`
  Source: https://github.com/pydantic/pydantic-ai/blob/main/pydantic_ai_slim/pydantic_ai/mcp.py
  Replacements:
  - stdio: `MCPToolset(StdioTransport(command='ha-mcp', args=[...], env=...))`
  - streamable-HTTP: `MCPToolset('http://host:9000/mcp')`
- So the wiring is: `MCPToolset(...).prefixed('ha').approval_required(_is_destructive)`.
  Use `.prefixed('ha')` for ha-mcp and `.prefixed(slug)` per skill. Confirm
  whether `.prefixed()` should wrap before/after `.approval_required()` — order
  matters for the name the callback sees; wrap `approval_required` **innermost**
  (on the raw MCPToolset, before prefixing) so the callback reads unprefixed
  names/annotations, or read `tool_def.metadata` (prefix-independent).

---

## 8. Session persistence — `ModelMessagesTypeAdapter` / `message_history`

> **SUPERSEDED (design decision):** The shipped Concierge design does **not**
> use `ModelMessagesTypeAdapter` / `message_history`. Instead it follows the
> AG-UI "client-owns-messages" model — each `RunAgentInput` carries the thread's
> messages, and the backend persists AG-UI wire-format (camelCase) message
> dicts, teeing the event stream into SQLite for cross-session rehydration. The
> `ModelMessagesTypeAdapter` verification below is retained for historical
> record only. See `docs/superpowers/plans/2026-07-10-concierge-backend.md`
> (Global Constraints: "No `ModelMessagesTypeAdapter`") and
> `docs/superpowers/notes/2026-07-10-backend-handoff.md`.

**Verdict: CONFIRMED.**

- `from pydantic_ai import ModelMessagesTypeAdapter, ModelMessage`. Serialize with
  `pydantic_core.to_json(result.all_messages())` (or `to_jsonable_python`);
  deserialize with `ModelMessagesTypeAdapter.validate_json(...)`. Pass the list to
  the next run via `message_history=`. Source:
  https://github.com/pydantic/pydantic-ai/blob/main/docs/message-history.md (2.8.0)
- Spec §5.4's "append `result.new_messages()` per turn, load full list as
  `message_history`" is exactly the documented pattern. Store
  `to_jsonable_python`/`to_json` output in the SQLite `message_json` column.
  `ModelMessage` is a discriminated union — the pre-built `ModelMessagesTypeAdapter`
  handles it; no custom schema needed.

---

## 9. Observability — OTel → Langfuse / Logfire

**Verdict: CONFIRMED.**

- Pydantic AI is OTel-instrumented. Enable globally with `Agent.instrument_all()`
  (or `Agent(..., instrument=True)`), then export via standard OTLP env vars to
  Langfuse's OTLP endpoint: `OTEL_EXPORTER_OTLP_ENDPOINT=<host>/api/public/otel`
  and `OTEL_EXPORTER_OTLP_HEADERS` (Basic auth: base64 `public:secret`). Custom
  providers via `InstrumentationSettings`. Logfire is the first-party alternative
  (`logfire.configure()` + `logfire.instrument_pydantic_ai()`).
- Sources: https://langfuse.com/integrations/frameworks/pydantic-ai ,
  https://pydantic.dev/docs/logfire/get-started/ai-observability/ , pydantic-ai
  issue #3580 (TemporalAgent OTel). Operator-configurable, off by default — matches spec §5.7.

---

## 10. §11 items resolvable now + surprises

**Resolved:**
- §11.2 transport → **stdio** (§6).
- §11.4 HITL-on-MCP seam → **solved** via `.approval_required()` + `tool_def.metadata['annotations']` (§1–2).
- §11.5 AG-UI client → **hand-parse SSE** recommended; `@ag-ui/client` 0.0.57 is a viable but heavier fallback (§5).
- §11.6 server-side resume state → **not needed** (§4); keep message history only.
- §11.1 default model IDs → provider/model still an operator option; pin actual
  Anthropic model IDs at build (the doc examples use placeholder `openai:gpt-5.2`
  — **do not** copy those). Pydantic AI supports `anthropic:*` natively.

**Still add-on-local (not a tooling question):** §11.3 container hostname suffix,
§11.7 `ingress_port` / `panel_icon`.

**SURPRISES / spec corrections to make:**
1. **`MCPServerStdio` / `MCPServerStreamableHTTP` are deprecated in v2** → use
   `MCPToolset` (+ `StdioTransport`). Update spec §5.2, §11.2. (biggest one)
2. **`tool_prefix` → `.prefixed('name')`** method in v2 (spec §5.2).
3. **HITL is not a bespoke wrapper** — it's the built-in `.approval_required(fn)`
   combinator; the callback reads `tool_def.metadata['annotations']`. Spec §5.5's
   "small toolset wrapper … confirmed at implementation" should be rewritten as
   "use `.approval_required()` reading MCP annotations" (now confirmed).
4. **`DeferredToolCalls` renamed to `DeferredToolRequests`** (v2.0.0); resume uses
   `deferred_tool_results=DeferredToolResults(approvals=...)` on the next run.
5. **`pending_approvals` table can be dropped** — resume is client-driven (§4).
6. **`@ag-ui/client` pulls RxJS** — non-trivial dependency weight for a Lit SPA;
   prefer hand-parsed SSE (§5).
7. **ha-mcp annotation coverage is not 100%** — gating must default missing
   annotations to "destructive/gated" (fail-safe), not "auto-run" (§2).
8. **Model-ID hygiene:** Pydantic AI's current docs use placeholder future IDs
   (`openai:gpt-5.2`, timestamps in examples) — treat as illustrative; pin real
   `anthropic:*` IDs verified at build time.
