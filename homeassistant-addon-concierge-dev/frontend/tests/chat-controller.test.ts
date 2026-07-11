import { expect, it } from "vitest";
import { ChatController } from "../src/state/chat-controller";
import type { AgUiEvent } from "../src/agui/events";
import type { RunAgentInput } from "../src/agui/api";

class FakeHost extends EventTarget {
  updates = 0;
  addController(): void {}
  removeController(): void {}
  requestUpdate(): void {
    this.updates++;
  }
  readonly updateComplete = Promise.resolve(true);
}

function scripted(...events: AgUiEvent[]) {
  const calls: RunAgentInput[] = [];
  async function* runFn(input: RunAgentInput) {
    calls.push(input);
    for (const ev of events) yield ev;
  }
  return { runFn, calls };
}

it("folds a plain text turn into messages", async () => {
  const { runFn } = scripted(
    { type: "RUN_STARTED" },
    { type: "TEXT_MESSAGE_START", messageId: "a1" },
    { type: "TEXT_MESSAGE_CONTENT", messageId: "a1", delta: "Hel" },
    { type: "TEXT_MESSAGE_CONTENT", messageId: "a1", delta: "lo" },
    { type: "TEXT_MESSAGE_END", messageId: "a1" },
    { type: "RUN_FINISHED" },
  );
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  await c.send("hi");
  expect(c.messages.at(0)).toMatchObject({ role: "user", content: "hi" });
  expect(c.messages.at(-1)).toMatchObject({ role: "assistant", content: "Hello" });
  expect(c.streaming).toBe(false);
  expect(c.error).toBeNull();
  expect(host.updates).toBeGreaterThan(2);
});

it("folds tool calls and results", async () => {
  const { runFn } = scripted(
    { type: "RUN_STARTED" },
    { type: "TOOL_CALL_START", toolCallId: "c1", toolCallName: "ha_search", parentMessageId: "a1" },
    { type: "TOOL_CALL_ARGS", toolCallId: "c1", delta: '{"query":"x"}' },
    { type: "TOOL_CALL_END", toolCallId: "c1" },
    { type: "TOOL_CALL_RESULT", messageId: "r1", toolCallId: "c1", content: "ok" },
    { type: "RUN_FINISHED" },
  );
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  await c.send("search");
  const assistant = c.messages.find((m) => m.role === "assistant");
  expect(assistant).toMatchObject({
    toolCalls: [{ id: "c1", function: { name: "ha_search", arguments: '{"query":"x"}' } }],
  });
  expect(c.messages.at(-1)).toMatchObject({ role: "tool", toolCallId: "c1", content: "ok" });
});

it("captures interrupts and resumes with approval", async () => {
  const interrupt = { id: "i1", toolCallId: "c1" };
  const turn1 = scripted(
    { type: "RUN_STARTED" },
    { type: "TOOL_CALL_START", toolCallId: "c1", toolCallName: "ha_call_service", parentMessageId: "a1" },
    { type: "TOOL_CALL_END", toolCallId: "c1" },
    { type: "RUN_FINISHED", outcome: { type: "interrupt", interrupts: [interrupt] } },
  );
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn: turn1.runFn });
  await c.openThread(null);
  await c.send("turn it off");
  expect(c.pendingInterrupts).toEqual([interrupt]);
  expect(c.streaming).toBe(false);

  const turn2 = scripted(
    { type: "RUN_STARTED" },
    { type: "TOOL_CALL_RESULT", messageId: "r1", toolCallId: "c1", content: "done" },
    { type: "RUN_FINISHED", outcome: { type: "success" } },
  );
  c.setRunFnForTests(turn2.runFn);
  await c.resolveInterrupt("i1", true);
  expect(turn2.calls[0]!.resume).toEqual([
    { interruptId: "i1", status: "resolved", payload: { approved: true } },
  ]);
  expect(turn2.calls[0]!.messages.length).toBeGreaterThan(0); // thread round-trip
  expect(c.pendingInterrupts).toEqual([]);
  expect(c.messages.at(-1)).toMatchObject({ role: "tool", content: "done" });
});

it("treats RUN_ERROR as turn-terminal", async () => {
  const { runFn } = scripted(
    { type: "RUN_STARTED" },
    { type: "TEXT_MESSAGE_CONTENT", messageId: "a1", delta: "partial" },
    { type: "RUN_ERROR", message: "boom" },
  );
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  await c.send("hi");
  expect(c.error).toBe("boom");
  expect(c.streaming).toBe(false);
  expect(c.messages.at(-1)).toMatchObject({ role: "assistant", content: "partial" });
});

it("rehydrates an existing thread", async () => {
  const loadFn = async () => [{ id: "u1", role: "user" as const, content: "old" }];
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn: scripted().runFn, loadFn });
  await c.openThread("t9");
  expect(c.threadId).toBe("t9");
  expect(c.messages).toHaveLength(1);
});
