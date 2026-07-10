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
