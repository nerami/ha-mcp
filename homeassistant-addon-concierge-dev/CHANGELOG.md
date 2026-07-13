# Changelog

## 0.1.0.dev6

- Harden the backend: pass the bundled ha-mcp subprocess a least-privilege
  environment allowlist instead of the full parent environment (no LLM
  provider key or other secrets leak into it), bound each skill-discovery
  probe with a per-attempt timeout, skip duplicate skills that collide on
  their normalized name, and serialize the SQLite session store across threads.
- Add a thread-rename affordance to the conversation sidebar.
- Documentation: cross-link the Concierge add-on from the repository guide and
  add a developer-workflow section (per-subproject test/lint commands and
  constraints).

## 0.1.0.dev1

- Initial dev-channel release: self-hosted chat concierge over ha-mcp, served
  through Home Assistant ingress. Streaming chat, tool-call rendering,
  human-in-the-loop approval for destructive actions, multi-thread history,
  and skill-add-on extensibility.
