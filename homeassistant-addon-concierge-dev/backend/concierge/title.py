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
