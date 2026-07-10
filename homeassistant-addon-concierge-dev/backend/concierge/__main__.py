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
