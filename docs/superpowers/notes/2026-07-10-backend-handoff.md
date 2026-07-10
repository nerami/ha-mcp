# Backend handoff notes — FE (Plan 2) and packaging (Plan 3)

Snapshot of `homeassistant-addon-concierge-dev/backend` on `feat/concierge-addon`
at the point the backend's final whole-branch review closed. State facts only —
see the review comments / commit history for rationale.

## FE wire contract (Plan 2)

- **Transport**: AG-UI over Server-Sent Events at `POST /agui`. Response
  `content-type` is always `text/event-stream` (`AGUIAdapter` / `EventEncoder`
  picks the wire format; this backend never negotiates a non-SSE alternative).
- **Run input**: standard `RunAgentInput` (`ag_ui.core`). `threadId` is
  **client-generated** — the backend never mints thread ids, it only accepts
  whatever the FE sends and stores against it (`concierge/web.py::run_agui`
  reads `run_input.thread_id` directly from the request body).
- **Resume (HITL) shape**, verified against the installed `ag_ui.core` /
  `pydantic_ai.ui.ag_ui._interrupt` models, not the original spec's provisional
  guess:
  ```jsonc
  "resume": [
    {
      "interruptId": "<id from RUN_FINISHED.outcome.interrupts[].id>",
      "status": "resolved",           // or "cancelled"
      "payload": {
        "approved": true,             // required; anything else = denial
        "editedArgs": { ... },        // optional, only applied when approved
        "reason": "..."               // optional, denial message
      }
    }
  ]
  ```
  `resume_entry_to_approval` requires `payload.approved is True` (exactly, not
  truthy) to treat the entry as an approval; a missing/false/non-bool
  `approved`, or a non-dict `payload`, is treated as a denial with `reason` (if
  present) surfaced as the denial message.
- **Interrupt outcome**: on a gated (destructive) tool call, the run ends with
  `RUN_FINISHED` and `outcome.type == "interrupt"`, `outcome.interrupts` a
  list of `{id, reason, message, toolCallId, responseSchema, expiresAt,
  metadata}`. No `TOOL_CALL_RESULT` event is emitted for a gated call on the
  turn that gates it — only after the FE resumes with approval does the tool
  actually execute and `TOOL_CALL_RESULT` appear (see
  `tests/test_hitl_flow.py`).
- **Mid-stream errors**: a turn that fails partway through still ends with a
  normal HTTP 200 SSE stream containing a `RUN_ERROR` event
  (`{"type": "RUN_ERROR", "message": "..."}`); `RUN_FINISHED` is **not** sent
  on that turn (pydantic-ai's `after_stream` hook short-circuits once an error
  has been recorded). Whatever assistant text had already streamed is still
  durably persisted server-side — see `tests/test_web.py::
  test_agui_persists_partial_text_on_mid_stream_error`.
- **Thread rehydration**: `GET /threads` returns the thread list (id + stored
  title); `GET /threads/{id}` returns the full stored message array as raw
  AG-UI message dicts (camelCase keys: `toolCalls`, `toolCallId`, etc. —
  round-trips directly back into a subsequent `RunAgentInput.messages`).
  `PATCH /threads/{id}` renames, `DELETE /threads/{id}` deletes.
- **Titles**: generated server-side, once, after the *first* turn on a new
  thread completes (skipped if a title already exists). The FE does not
  receive the title inline on the SSE stream — it only becomes visible via a
  `GET /threads` refresh. Because title generation runs inside the same
  request's `finally` block (`_maybe_title`, awaited after all SSE events have
  been yielded), the HTTP response for that first turn stays open for
  roughly one extra title-model round-trip *after* the client sees
  `RUN_FINISHED` — the FE should not assume the connection closes the instant
  `RUN_FINISHED` arrives.

## Toolset lifecycle

Fixed in this pass (`perf(concierge): hold MCP toolset contexts open for the
app lifetime`): `concierge/web.py::create_app` now installs a FastAPI
`lifespan` that does `async with agent:` for the whole app lifetime.
`Agent.__aenter__` (pydantic-ai 2.8.0) enters every registered toolset (and
the model) once. Each individual `POST /agui` call still enters/exits its
toolsets internally via `run_stream`, but `MCPToolset` ref-counts entry via
`_running_count`, so with the lifespan holding it open at 1, a per-run
enter/exit is a cheap no-op instead of a real reconnect. Concretely: the
bundled ha-mcp stdio subprocess (and any skill add-on's streamable-HTTP
connection) is spawned/connected once at process startup, not on every turn.
Verified directly against the ref-count, not by timing:
`tests/test_web.py::test_lifespan_holds_toolset_open_across_turns` asserts
the stub toolset's `_running_count` sits at 1 both before and after two
consecutive `POST /agui` turns.

## Plan 3 (packaging) security note

`POST /agui` (and the rest of the FastAPI app) has **no authentication** and
`Settings.host` defaults to `0.0.0.0`. This is intentional under the current
threat model — the add-on is meant to be reached only through Supervisor
ingress, which terminates on loopback/private networking and handles the
"who's allowed to open the panel" question upstream. But two things follow
that Plan 3 must respect:

- **Do not map the port in `config.yaml`.** Publishing it (`ports:` /
  `host_network: true`) would expose an unauthenticated endpoint on the LAN.
- **The approver of every gated (destructive) tool call is simply "whoever
  can reach `/agui`."** On the shared `hassio` network, any other add-on
  container can reach this add-on's internal port even without a host port
  mapping. If that's an acceptable boundary for launch, fine — but Plan 3
  should explicitly consider ingress-source filtering (verifying the request
  came through Supervisor's ingress proxy) or a secret path segment
  (mirroring the `MCP_SECRET_PATH` pattern the main `ha-mcp` add-on already
  uses for its own HTTP mode) rather than relying on "nobody happens to probe
  the port" by default.

## Plan 3 hardening backlog

Concrete, verified gaps to close during packaging — not blocking, but real:

- **No per-attempt timeout on skill probes.** `concierge/skills.py::
  probe_endpoint` retries `_PROBE_ATTEMPTS = 3` times with a
  `_PROBE_DELAY_SECONDS = 1.5` gap between attempts, but each
  `async with MCPToolset(url):` connect attempt itself has no bound — a
  skill add-on that accepts the TCP connection but never completes the MCP
  handshake can hang a single attempt indefinitely, not just the 3×1.5s the
  retry loop budgets for. Wrap each attempt in `asyncio.timeout(...)`.
- **Full `os.environ` spread into the ha-mcp subprocess.**
  `concierge/agent.py::build_hamcp_toolset` builds the subprocess env as
  `{**os.environ, "HOMEASSISTANT_URL": ..., "HOMEASSISTANT_TOKEN": ...}` —
  every secret/variable in Concierge's own environment (including
  `CONCIERGE_API_KEY`) is currently inherited by the child process. Should be
  a least-privilege allowlist instead.
- **Skills are resolved once at startup, never re-probed.**
  `concierge/agent.py::build_agent` calls `resolve_skills` exactly once
  during agent construction; there is no retry/refresh loop. If a skill
  add-on boots slower than Concierge (cold start race) or restarts later,
  Concierge will not pick it up until *Concierge itself* is restarted. Worth
  a documented operational note at minimum, ideally a supervised re-probe.
- **No `skill_name` collision detection.** `concierge/skills.py::skill_name`
  normalizes an entry to a prefix by replacing `-` with `_` (e.g. `"my-skill"`
  and `"my_skill"` both become `"my_skill"`). Two configured skills that
  collide after normalization will silently produce two toolsets registered
  under the same prefix with no warning; `resolve_skills` should dedupe or
  warn.
