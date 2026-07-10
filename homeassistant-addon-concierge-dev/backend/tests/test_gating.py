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
