"""Accumulate a run's AG-UI events into AG-UI wire-format messages.

AG-UI is client-owns-messages: RunAgentInput carries the prior thread. This
tee reconstructs the new assistant/tool messages from the streamed events so
the server can persist the full thread once at stream end. Dict keys use the
protocol's camelCase so stored messages round-trip through RunAgentInput
unchanged.
"""

from __future__ import annotations

import copy
from typing import Any

_TEXT_START = "TEXT_MESSAGE_START"
_TEXT_CONTENT = "TEXT_MESSAGE_CONTENT"
_TOOL_START = "TOOL_CALL_START"
_TOOL_ARGS = "TOOL_CALL_ARGS"
_TOOL_RESULT = "TOOL_CALL_RESULT"


def _event_type(event: Any) -> str:
    raw = getattr(event, "type", "")
    return getattr(raw, "value", raw) or ""


class MessageAccumulator:
    def __init__(self, initial_messages: list[dict[str, Any]]) -> None:
        self._messages: list[dict[str, Any]] = [
            copy.deepcopy(m) for m in initial_messages
        ]
        self._by_id: dict[str, dict[str, Any]] = {
            str(m["id"]): m for m in self._messages if "id" in m
        }
        self._tool_calls: dict[str, dict[str, Any]] = {}

    def _message(self, message_id: str, role: str) -> dict[str, Any]:
        message = self._by_id.get(message_id)
        if message is None:
            message = {"id": message_id, "role": role, "content": ""}
            self._messages.append(message)
            self._by_id[message_id] = message
        return message

    def feed(self, event: Any) -> None:
        kind = _event_type(event)
        if kind == _TEXT_START:
            self._message(event.message_id, getattr(event, "role", "assistant"))
        elif kind == _TEXT_CONTENT:
            message = self._message(event.message_id, "assistant")
            message["content"] = str(message.get("content") or "") + event.delta
        elif kind == _TOOL_START:
            parent_id = getattr(event, "parent_message_id", None) or event.tool_call_id
            message = self._message(parent_id, "assistant")
            call = {
                "id": event.tool_call_id,
                "type": "function",
                "function": {"name": event.tool_call_name, "arguments": ""},
            }
            message.setdefault("toolCalls", []).append(call)
            self._tool_calls[event.tool_call_id] = call
        elif kind == _TOOL_ARGS:
            tool_call = self._tool_calls.get(event.tool_call_id)
            if tool_call is not None:
                tool_call["function"]["arguments"] += event.delta
        elif kind == _TOOL_RESULT:
            self._messages.append(
                {
                    "id": event.message_id,
                    "role": "tool",
                    "toolCallId": event.tool_call_id,
                    "content": event.content,
                }
            )

    def messages(self) -> list[dict[str, Any]]:
        return self._messages
