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


def test_initial_messages_are_not_mutated_on_id_collision() -> None:
    original = {"id": "a1", "role": "assistant", "content": "partial"}
    acc = MessageAccumulator([original])
    acc.feed(TextMessageContentEvent(message_id="a1", delta=" more"))
    assert original == {"id": "a1", "role": "assistant", "content": "partial"}
    assert acc.messages()[0]["content"] == "partial more"
