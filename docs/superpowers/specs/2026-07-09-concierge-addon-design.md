# Concierge Add-on — Design Spec

- **Date:** 2026-07-09
- **Status:** Draft (hardened by codebase + tooling verification) — pending author review
- **Branch:** `feat/concierge-addon`
- **Slugs:** `ha_mcp_concierge` (stable, `homeassistant-addon-concierge/`) + `ha_mcp_concierge_dev` (dev, `homeassistant-addon-concierge-dev/`) — dev-first / promote-only (§8)
- **Pinned versions** (verified 2026-07-09): `pydantic-ai-slim[ag-ui,mcp]` **2.8.0** · `ha-mcp` **7.12.0** · `ag-ui-protocol` **0.1.19** (Python `ag_ui.core`, via the `ag-ui` extra) · `@ag-ui/client` **0.0.57** (fallback only — §6.2). See `docs/superpowers/notes/2026-07-09-tooling-verification.md`.

## 1. Summary

A new, **completely optional** Home Assistant add-on that ships beside
`homeassistant-addon`. It provides a **chat concierge**: a self-hosted,
mobile-friendly conversational UI over the user's smart home, reachable from the
Home Assistant companion app via Supervisor **ingress**.

The agent is a **new backend built on Pydantic AI** (provider-agnostic — any
high-quality, tool-capable LLM; Claude by default), whose
toolset is **ha-mcp itself**, bundled and run in-container as an MCP server. The
frontend is built the **Home Assistant way**: **Lit** web components + the HA
design system (Vite → static bundle, served by FastAPI), talking to the backend
over the **AG-UI protocol** — Pydantic AI's native agent-UI event stream,
hand-parsed from Lit without React. No React, no Vercel AI SDK, no RxJS.

## 2. Motivation & positioning

- **ha-mcp already works without a UI.** Its value is exposing MCP tools to
  Claude and other agents. Concierge does **not** replace that; it is a
  *complementary* delivery — the self-hosted, phone-accessible face for users
  who don't want to wire up an external agent.
- **The appeal:** one install → a chat UI you can open from your phone through
  the HA app, with all of ha-mcp's capabilities behind it.
- **Community-fit is the north star.** The FE must read as "yes, that's how a
  Home Assistant plugin is built" — HA conventions front to back, not a React
  app parachuted into the HA ecosystem.

## 3. Goals & non-goals

**Goals (v1):**
- Streaming chat with a high-quality, tool-capable LLM (provider-agnostic;
  Claude by default).
- Tool-call rendering (what the agent is doing, live).
- Human-in-the-loop (HITL) approval for destructive tools.
- Multi-thread history with auto-generated titles, persisted **locally**.
- Runs on constrained HA hardware (e.g. HA Green: aarch64, 4 GB RAM, eMMC).
- Extensible: third parties can add "skills" as separate MCP add-ons.
- Self-contained: a single add-on install; no dependency on the `ha_mcp` add-on.

**Non-goals (v1 — deferred):**
- Server-driven / generative UI components.
- Voice input / TTS (HA Assist pipeline integration).
- Robustness for weak / small / local models — v1 **assumes a high-quality,
  tool-capable model** (Claude / GPT-4-class / Gemini / Mistral Large). No
  capability probe or weak-model degradation.

## 4. Architecture

### 4.1 Repository layout

```
homeassistant-addon-concierge/          # STABLE flavor (promote-only; never hand-edited)
homeassistant-addon-concierge-dev/      # DEV flavor (canonical; all changes land here)
  ├── config.yaml                       # ingress, panel_icon, options (skills, model, …)
  ├── Dockerfile                        # bundles ha-mcp + backend + Vite-built FE
  ├── backend/                          # Pydantic AI service (Python 3.13)
  │   ├── agent.py     # Agent(model), system prompt, MCP toolsets, approval callback
  │   ├── skills.py    # skill discovery (MCP-over-DNS, per-skill degradation)
  │   ├── sessions.py  # SQLite thread/message store in /data
  │   ├── web.py       # FastAPI: AG-UI run endpoint + thread CRUD + serve SPA
  │   └── title.py     # auto-title (cheap model)
  └── frontend/        # Lit + TS; Vite build → static bundle (served by web.py)
      ├── src/ …
      ├── package.json # tooled like site/ (npm + TS + eslint)
      └── vite.config.ts
# The promote workflow syncs the dev flavor → stable (§8); stable is never hand-edited.
```

### 4.2 Components

1. **Backend (Pydantic AI).** One `Agent` bound to Claude. Toolsets = **bundled
   ha-mcp** (always present) + discovered skill add-ons — all attached through
   the *same* `MCPToolset` abstraction. Sessions in SQLite. HITL via the
   `MCPToolset.approval_required(...)` combinator (§5.5). OTel-instrumented.
2. **Frontend (Lit).** Chat panel, streaming renderer, tool-call cards, HITL
   approve/deny UI, thread sidebar. Hand-parses the **AG-UI** SSE event stream. Reads the
   active HA theme and applies matching CSS variables so it looks native inside
   the ingress iframe.
3. **Skill discovery (`skills.py`).** Resolves and mounts skill add-ons over MCP.
4. **Skill add-ons.** The extensibility surface (the pixoo/divoom pattern):
   any FastMCP add-on lights up as concierge tools.

### 4.3 Data flow (one turn)

```
FE  POST /agui  (RunAgentInput: threadId + new message)
      → backend loads thread history from SQLite (ModelMessage[])
      → AGUIAdapter runs the agent over [ha-mcp + skills]
      → AG-UI SSE: RUN_STARTED · TEXT_MESSAGE_* · TOOL_CALL_* · TOOL_CALL_RESULT · RUN_FINISHED
      → FE renders live
      → on finish: persist new messages; new thread → generate title server-side
        (FE picks it up via thread-list refresh or a CUSTOM event)
HITL: destructive tool → RUN_FINISHED{outcome:"interrupt"} lists approvals
      → FE approve/deny → POST /agui (RunAgentInput + resume[]) → run continues
```

## 5. Backend design (Pydantic AI)

### 5.1 Agent & model

- Single `pydantic_ai.Agent` bound to a model built from generic provider
  options — **provider-agnostic by design** (Pydantic AI supports Anthropic,
  OpenAI, Google, Groq, Mistral, and Bedrock natively, plus any
  **OpenAI-compatible** endpoint incl. local Ollama / vLLM / LM Studio via
  `base_url`).
- A small **model-builder** maps options → the Pydantic AI model object.
  **Default: Anthropic/Claude** (best tool-calling).
- v1 **targets the high-quality tier** and assumes reliable tool calling +
  tool-call streaming; no capability probing or weak-model fallbacks (see §3
  non-goals). Provider-locked optimizations (e.g. Anthropic prompt caching) stay
  opt-in, never core.
- Chat and title models are configured independently (`model` / `title_model`,
  the latter falling back to `model`).
- **Exact default model IDs are pinned at implementation time** (verify then).
- System prompt carries the provider-agnostic discovery policy (resolve unknown
  ids via whatever search/list tools are mounted; ask the user when none can);
  expect minor per-model-family prompt tweaks.

### 5.2 Tool sources — bundled ha-mcp + skills, one abstraction

- **ha-mcp is bundled** (PyPI package inside the container) and run as an
  **in-container MCP server**, attached via Pydantic AI's `MCPToolset`. This keeps
  Concierge self-contained (one install) while respecting ha-mcp's MCP boundary
  (its tool curation, config, and safety annotations come through unchanged).
  - **Transport: stdio** (`MCPToolset(StdioTransport(...))`, running ha-mcp's
    stdio entrypoint). Verified preferable to HTTP: ha-mcp's HTTP mode needs
    `MCP_SECRET_PATH` + an origin guard + a port for zero benefit here, and its
    stdin check accepts a FIFO pipe.
- **Skills** are additional `MCPToolset`s (HTTP transport to the skill add-ons,
  §5.3) attached to the same agent. ha-mcp is simply "the skill that is always
  present."
- Each **skill** toolset is namespaced with **`.prefixed('<slug>')`** (v2 API) so
  tool-name collisions across servers are avoided automatically. The bundled
  ha-mcp toolset is **not** prefixed — its tools already carry the `ha_*`
  namespace (prefixing would yield `ha_ha_*`).
- *(API note: `MCPServerStdio` / `MCPServerStreamableHTTP` are deprecated in
  Pydantic AI v2 in favor of `MCPToolset` + transports.)*

### 5.3 Skill discovery (`skills.py`)

Skill discovery works as follows:

- A **skill** is a separate HA add-on running a FastMCP streamable-HTTP server on
  `:9000/mcp`, named `ha-concierge-skill-<slug>`.
- The operator lists **short slugs** in the `skills` add-on option.
- The backend derives the Supervisor repo prefix from its **own hostname**
  (`<prefix>-ha_mcp_concierge` → `<prefix>`; exact suffix confirmed against the
  built add-on's DNS name at implementation) and resolves each slug to
  `http://<prefix>-ha-concierge-skill-<slug>:9000/mcp`. **Zero Supervisor
  privilege** — pure Docker DNS.
- A full `http(s)://…/mcp` entry is honored verbatim (cross-repo escape hatch).
- **Per-skill graceful degradation:** one unreachable skill logs a warning and
  is skipped; the others (and bundled ha-mcp) are unaffected.
- **Bounded startup retry** + a **process-lifetime cache** with backoff on
  failure (ported behavior).
- Injectable client factory as a test seam (ported).

### 5.4 Sessions (local persistence)

- **SQLite** file on the add-on's `/data` volume (survives restarts; captured in
  HA backups). **WAL** mode.
- Schema:
  - `threads(id TEXT PK, title TEXT, created_at, updated_at)`
  - `messages(thread_id, seq, message_json)` — `message_json` is an **AG-UI
    message** (the protocol's own wire format, camelCase JSON).
  - *(No `pending_approvals` table.)* AG-UI's interrupt/resume is **client-driven**
    — the FE resends `RunAgentInput` carrying the approvals, so only message
    history is persisted server-side.
- **AG-UI is client-owns-messages:** each `RunAgentInput` carries the thread's
  full message list, which the adapter converts into the run's history — the
  server does not inject `message_history` itself. Server-side persistence is a
  **tee on the event stream**: accumulate the run's AG-UI events into messages
  and write the thread once at `RUN_FINISHED`/`RUN_ERROR`. The store's job is
  cross-session **rehydration** (`GET /threads/{id}`), after which the client
  round-trips the messages.
- **One write per turn, not per step** — keeps disk churn low; friendly to eMMC.

### 5.5 Human-in-the-loop

- **Approval policy is derived, not hand-maintained.** ha-mcp tools carry MCP
  safety annotations (`readOnlyHint`, `destructiveHint`). Concierge routes:
  read-only → auto-run; destructive/write → approval-required.
- **Mechanism (verified):** the agent's `output_type` includes
  `DeferredToolRequests`, and gated calls route through **AG-UI's interrupt
  lifecycle** — the run pauses and the SSE stream ends with
  `RUN_FINISHED { outcome.type: "interrupt" }` listing pending approvals. The FE
  renders approve/deny and POSTs the next `RunAgentInput` whose `resume` entries
  carry `{approved, editedArgs?, reason?}`; the backend resumes via
  `DeferredToolResults(approvals=…)` and the run continues.
- **MCP-tool gating — solved, no bespoke wrapper.** Pydantic AI v2 ships
  **`MCPToolset.approval_required(func)`**, where `func(ctx, tool_def, tool_args)
  -> bool` decides per call and routes `True` into the same `DeferredToolRequests`
  machinery. The callback reads the MCP annotation off
  **`tool_def.metadata['annotations']`** (`destructiveHint` / `readOnlyHint`) —
  Pydantic AI's MCP client surfaces it. ha-mcp sets these annotations (92 sites),
  but coverage isn't total, so **default missing/unknown annotations to gated**
  (fail-safe). Confirm the exact annotation key casing with one live `tools/list`
  wiring test (§10).
- A global **`auto_run_tools`** option (default `false`) overrides to auto-run
  everything.

### 5.6 Streaming

- The backend uses Pydantic AI's **`AGUIAdapter`** to run the agent and emit the
  AG-UI SSE event stream — no hand-written event mapper. Either
  `AGUIAdapter.dispatch_request(request, agent=...)` (one call) or the manual
  `build_run_input` → `run_stream()` → `encode_stream()` form for custom FastAPI
  wiring (both documented).
- Not every provider streams *partial tool-call args*; the FE renders a
  tool-call card once `TOOL_CALL_END` lands, so streaming variance degrades
  cleanly.
- Partial assistant text is persisted even if a turn errors mid-stream, so a
  dropped turn is not lost.

### 5.7 Observability

- Pydantic AI is **OpenTelemetry-instrumented**. Export OTel traces to
  **Langfuse**, or use **Logfire**. Operator-configurable; disabled by default.

## 6. Frontend design (Lit)

### 6.1 Stack & constraints

- **Lit + TypeScript**, built with **Vite** to a static bundle that FastAPI
  serves — **tooled like the repo's `site/`** (npm + TS + eslint + build step),
  *not* like `settings_ui` (hand-written, no build). Component structure while
  keeping "no runtime build dependency in the shipped image."
- **Sole runtime dependency is Lit.** The AG-UI stream is hand-parsed (§6.2), so
  **no `@ag-ui/client`** (it pulls in RxJS — too heavy for this bundle), **no**
  React, `@ai-sdk/*`, `@langchain/langgraph-sdk`, or CopilotKit.
- **Inherit `settings_ui`'s CI-enforced constraints** where they apply: the
  anti-FOUC theme-resolution pattern (`test_anti_fouc_parity.py`) and the a11y
  rules (native semantics, landmarks, `role`/`aria-live`); the repo's JS-harness
  auto-discovers new script surfaces.
- Runs in the **ingress iframe**, so it cannot reach HA's in-process `hass`
  object or reuse real `ha-*` elements; it **matches** the design system and
  talks to HA over the API.

### 6.2 Agent transport — hand-parsed AG-UI SSE (no React, no RxJS)

- An `AgentController` (Lit `ReactiveController`) speaks the **AG-UI protocol**:
  it POSTs a `RunAgentInput` and reads the AG-UI **SSE** event stream via
  `fetch` + `response.body.getReader()` + `TextDecoder`, updating reactive state
  the Lit components render. AG-UI's event enum (`TEXT_MESSAGE_*`, `TOOL_CALL_*`,
  `RUN_*`) is stable and small, so hand-parsing is a few dozen lines.
- **`@ag-ui/client` is *not* used** by default: its `HttpAgent` drags in **RxJS**,
  disproportionately heavy for this bundle. It stays a documented fallback only.
- `EventSource` is unsuitable regardless (GET-only; AG-UI POSTs `RunAgentInput`).
- CopilotKit and other AG-UI **React** bindings are deliberately not used.

### 6.3 Theme

- **v1:** `prefers-color-scheme` default + a manual light/dark toggle persisted
  in `localStorage`, stamped as `data-theme` on `<html>` by an inline
  **anti-FOUC** script before first paint (the `settings_ui` pattern). This
  matches HA's default follow-the-OS behavior. Inside the ingress iframe there
  is no `hass` object and no token, so reading the user's *actual* active HA
  theme is not feasible client-side in v1 — `home-assistant-js-websocket` is
  therefore **not** a v1 dependency.
- **Future:** true HA-theme sync via a small backend proxy endpoint (the
  backend holds `ha_url`/`ha_token`) — deferred.

### 6.4 Components

- Thread sidebar (list, new, rename, delete).
- Message list + streaming assistant renderer (Markdown).
- Tool-call cards (name, args, result state).
- HITL approval control (approve / deny; the wire contract supports
  `editedArgs`, but an arg-editing UI is deferred past v1).

## 7. Wire contract

The turn stream **is the AG-UI protocol** (SSE) — we don't define our own event
schema. Around it we layer a thin REST surface for thread persistence (AG-UI does
not own storage) and static serving.

### 7.1 AG-UI turn stream

- **Transport:** SSE (`text/event-stream`); request body is a `RunAgentInput`
  (thread id, the new/replayed messages, and on resume a `resume[]` array).
- **Events consumed by the FE** (standard AG-UI): `RUN_STARTED` /
  `RUN_FINISHED` (incl. `outcome.type: "interrupt"` for HITL) / `RUN_ERROR`;
  `TEXT_MESSAGE_START` / `_CONTENT` / `_END`; `TOOL_CALL_START` / `_ARGS` /
  `_END` and `TOOL_CALL_RESULT`; optionally `STATE_SNAPSHOT` / `STATE_DELTA`
  (reserved for the deferred generative UI) and `CUSTOM`.
- **Persistence is server-side:** the backend tees the event stream and writes
  the turn's messages into SQLite keyed by the `RunAgentInput` thread id (§5.4);
  AG-UI carries the turn, our store owns cross-session rehydration.

### 7.2 REST surface around AG-UI (FastAPI)

- `POST /agui` → the AG-UI run endpoint (new turns *and* resumes; a resume is a
  `RunAgentInput` whose `resume` entries carry `{approved, editedArgs?, reason?}`).
- `GET /threads` → thread list (id, title, timestamps).
- `GET /threads/{id}` → messages for rehydration.
- `PATCH /threads/{id}` `{title}` / `DELETE /threads/{id}`.
- Auto-title for a new thread is generated **server-side** (ours, not AG-UI's)
  and surfaced to the FE via a thread-list refresh or a `CUSTOM` AG-UI event.
- `GET /{path}` → serve the built Lit SPA (registered last; never shadows API).

## 8. Add-on packaging

- **Two flavors, dev-first / promote-only** (mirrors the Webhook Proxy addon):
  `homeassistant-addon-concierge-dev/` is the *only* flavor edited directly;
  `homeassistant-addon-concierge/` (stable) is updated solely via a manual
  promote workflow behind a versioning guard. **Read
  `homeassistant-addon-webhook-proxy/AGENTS.md` before implementing** — it owns
  the exact flavor / versioning / promote flow to copy.
- **`config.yaml`:** `ingress: true`, `ingress_port`, `panel_icon`,
  `homeassistant_api: true`, arch `aarch64` + `amd64`. No `host_network` unless a
  concrete need appears. Functional config is hand-maintained per flavor.
- **Options (initial):** `skills: []`, `auto_run_tools: false`, and a **generic
  model block** — `provider`, `model`, `api_key`, `base_url?` (for
  OpenAI-compatible / local endpoints), plus an optional `title_model` (falls
  back to `model`) — tracing toggles, `log_level`. Anthropic is the default
  provider. Per-provider curated fields are intentionally avoided in favor of the
  generic block, which covers the whole high-quality long tail (incl. local).
- **Dockerfile:** installs `ha-mcp` (7.12.0) + `pydantic-ai-slim[ag-ui,mcp]`
  (2.8.0) + the backend, copies the Vite-built Lit bundle, runs the FastAPI app.
- **Repo tooling:** add the backend package to the `mypy` / `ruff` target lists
  in `lefthook.yml` as a dedicated parallel job (the way
  `homeassistant-addon-webhook-proxy/start.py` gets its own) — it is not folded
  into `src/` linting automatically.

## 9. Error handling & degradation

- **Skills:** one unreachable skill logs + is skipped; bundled ha-mcp always
  present.
- **Streaming:** model/API errors surface as AG-UI `RUN_ERROR`; tool failures
  surface as `TOOL_CALL_RESULT` with an error payload. The turn ends gracefully
  and partial assistant text is saved.
- **Structured errors** throughout the backend (new codebase — adopt a clean,
  consistent error shape from the start).

## 10. Testing strategy

- **Layout:** the backend is a **self-contained uv project** with its own
  `tests/` inside the addon dir (the repo-root `tests/` project runs under the
  root env, which does not — and should not — carry `pydantic-ai`). Repo-wide
  container/integration tests stay in `tests/src/e2e/` for the packaging phase.
  Repo test rules apply either way (no broad `except` inside polling loops).
- **Backend (pytest):** Pydantic AI `TestModel` / `FunctionModel` (no live LLM)
  for agent wiring, toolset mounting + `.prefixed()`, the HITL approve/resume
  path, and a session round-trip (persist → rehydrate → continue). Skill
  discovery via the injectable client factory + a fake MCP server.
- **Annotation-casing wiring test:** one live `tools/list` against bundled ha-mcp
  asserting the exact `metadata['annotations']` key casing the approval callback
  keys off (§5.5) — the one live check the verification flagged.
- **Frontend:** Lit component tests (Vitest + happy-dom / `@open-wc/testing`) for
  message rendering, **AG-UI event** parsing, and the approval UI.
- **Integration:** a light end-to-end with `TestModel` + a stub ha-mcp MCP
  server, asserting the **AG-UI event sequence** (incl. an interrupt/resume).

## 11. To pin at implementation

**Resolved by verification** (see notes doc): MCP-tool gating
(`MCPToolset.approval_required` + `metadata['annotations']`, §5.5); transport
(stdio, §5.2); AG-UI client (hand-parsed SSE, §6.2); no `pending_approvals`
(§5.4); versions pinned (header).

**Genuinely open — settle during implementation:**
1. Real `anthropic:*` model IDs for chat + titles (docs use placeholder future
   IDs like `openai:gpt-5.2`; pin real ones at build).
2. Confirm the add-on's actual container hostname suffix for repo-prefix
   derivation in `skills.py` (one live check).
3. Confirm the exact `metadata['annotations']` key casing via the wiring test
   (§10) before trusting the gating callback.
4. `ingress_port` value and `panel_icon` choice.
5. Adopt the Webhook Proxy dev-first / promote CI flow (workflow + versioning
   guard) for the two flavors (§8).

## 12. Out of scope / future

- Generative / server-driven UI components.
- Voice (HA Assist pipeline) input/output.
- A companion Lovelace **card** (embed the concierge in dashboards) — appealing
  to the HA community, but a phase-2 delivery on top of the panel.
