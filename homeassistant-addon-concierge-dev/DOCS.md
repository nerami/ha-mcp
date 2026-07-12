# Concierge for HA MCP (Dev)

A self-hosted chat concierge for your smart home. It's a conversational
assistant — backed by an LLM of your choice and the full [ha-mcp](https://github.com/homeassistant-ai/ha-mcp)
tool set — that runs entirely inside your Home Assistant instance. No external
agent, cloud relay, or separate account is required.

> **Dev channel.** This is the experimental/unstable build, used to test
> changes before they reach the stable add-on. Expect rough edges and
> occasional breaking changes between versions.

## What it does

Open the add-on's **Web UI** (or the sidebar panel, once pinned) from the Home
Assistant app to chat with your home: ask about entity states, run scenes,
create or edit automations, manage helpers, and more — the same capabilities
ha-mcp exposes to any MCP client, now with a built-in chat front end.

## Configuration

Set these under the add-on's **Configuration** tab before starting it:

- **LLM provider** — `anthropic` (default), `openai`, `google`, `groq`,
  `mistral`, `bedrock`, or a custom OpenAI-compatible endpoint.
- **Chat model** — the model id used for conversation (e.g.
  `claude-sonnet-5`). Pick a high-quality, tool-capable model — the concierge
  relies on tool-calling to act on your home.
- **Title model** (optional) — a cheaper model used only to name new
  conversation threads. Leave blank to use a sensible default for your
  provider.
- **API key** — the credential for your chosen provider. Not required for
  providers that authenticate another way (e.g. AWS Bedrock's ambient
  credentials).
- **Base URL** (optional) — for OpenAI-compatible or local endpoints (Ollama,
  vLLM, OpenRouter, etc.). Leave blank for native providers.
- **Auto-run all tools** — off by default. When off, the concierge asks for
  your approval before running any destructive action (e.g. deleting an
  automation, turning something off). Turn this on only if you trust it to
  act without confirmation.
- **Skill add-ons** — slugs of installed `ha-concierge-skill-*` add-ons (or
  full `http(s)://…/mcp` URLs) to mount as additional tools, one per line.
- **Enable tracing** — off by default. Exports OpenTelemetry traces if you
  point the standard `OTEL_EXPORTER_OTLP_*` environment variables at an
  observability backend (e.g. Langfuse, Logfire).
- **Log level** — add-on log verbosity: `debug`, `info` (default), `warning`,
  or `error`.

## Access

The add-on is reachable only through Home Assistant's **ingress** proxy — it
is not exposed on your LAN or the internet. Open it from the add-on's **Open
Web UI** button, or pin it to the sidebar as a panel.

## Approval model

By default, the concierge pauses and asks before performing any action it
classifies as destructive (deleting, disabling, or otherwise changing
something in a way that's hard to undo). You approve or reject each request
in the chat. Enable **Auto-run all tools** to skip these prompts — recommended
only once you're comfortable with what the concierge does on its own.

## Support

This is an unstable dev build — please report issues against the
[ha-mcp repository](https://github.com/homeassistant-ai/ha-mcp/issues) and
mention you're running the **Concierge (Dev)** add-on and its version.
