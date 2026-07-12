import { expect, it } from "vitest";
import { ChatController } from "../src/state/chat-controller";
import type { AgUiEvent } from "../src/agui/events";
import type { ChatMessage, RunAgentInput } from "../src/agui/api";

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
  let finished = 0;
  host.addEventListener("turn-finished", () => finished++);
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  await c.send("hi");
  expect(c.messages.at(0)).toMatchObject({ role: "user", content: "hi" });
  expect(c.messages.at(-1)).toMatchObject({ role: "assistant", content: "Hello" });
  expect(c.streaming).toBe(false);
  expect(c.error).toBeNull();
  expect(host.updates).toBeGreaterThan(2);
  expect(finished).toBe(1); // clean finish fires turn-finished once
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
  let finished = 0;
  host.addEventListener("turn-finished", () => finished++);
  const c = new ChatController(host as never, { runFn: turn1.runFn });
  await c.openThread(null);
  await c.send("turn it off");
  expect(c.pendingInterrupts).toEqual([interrupt]);
  expect(c.streaming).toBe(false);
  expect(finished).toBe(1); // interrupt finish still fires turn-finished (title refresh)

  const turn2 = scripted(
    { type: "RUN_STARTED" },
    { type: "TOOL_CALL_RESULT", messageId: "r1", toolCallId: "c1", content: "done" },
    { type: "RUN_FINISHED", outcome: { type: "success" } },
  );
  c.setRunFnForTests(turn2.runFn);
  await c.resolveInterrupt("nope", true); // unknown id: no-op, no resume sent
  expect(turn2.calls).toHaveLength(0);
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
  let finished = 0;
  host.addEventListener("turn-finished", () => finished++);
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  await c.send("hi");
  expect(c.error).toBe("boom");
  expect(c.streaming).toBe(false);
  expect(c.messages.at(-1)).toMatchObject({ role: "assistant", content: "partial" });
  expect(finished).toBe(0); // RUN_ERROR must not fire turn-finished
});

it("rehydrates an existing thread", async () => {
  const loadFn = async () => [{ id: "u1", role: "user" as const, content: "old" }];
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn: scripted().runFn, loadFn });
  await c.openThread("t9");
  expect(c.threadId).toBe("t9");
  expect(c.messages).toHaveLength(1);
});

it("discards a stale in-flight turn when openThread switches threads", async () => {
  let releaseGate!: () => void;
  const gate = new Promise<void>((resolve) => (releaseGate = resolve));
  let reachedGate!: () => void;
  const atGate = new Promise<void>((resolve) => (reachedGate = resolve));
  async function* runFn(): AsyncGenerator<AgUiEvent> {
    yield { type: "RUN_STARTED" };
    yield { type: "TEXT_MESSAGE_CONTENT", messageId: "a1", delta: "stale" };
    reachedGate();
    await gate;
    yield { type: "TEXT_MESSAGE_CONTENT", messageId: "a1", delta: " never" };
    yield { type: "RUN_FINISHED" };
  }
  const host = new FakeHost();
  let finished = 0;
  host.addEventListener("turn-finished", () => finished++);
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  const sendPromise = c.send("hi");
  await atGate; // stream is mid-turn, paused inside the generator
  await c.openThread(null); // user switches to a new thread
  releaseGate();
  await sendPromise;
  expect(c.messages).toEqual([]); // no stale folds leak into the new thread
  expect(c.streaming).toBe(false);
  expect(finished).toBe(0); // stale turn must not emit turn-finished
});

it("suppresses a stale turn's error after openThread switches threads", async () => {
  let releaseGate!: () => void;
  const gate = new Promise<void>((resolve) => (releaseGate = resolve));
  let reachedGate!: () => void;
  const atGate = new Promise<void>((resolve) => (reachedGate = resolve));
  async function* runFn(): AsyncGenerator<AgUiEvent> {
    yield { type: "RUN_STARTED" };
    reachedGate();
    await gate;
    throw new Error("stale failure");
  }
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  const sendPromise = c.send("hi");
  await atGate;
  await c.openThread(null); // switch threads while the stale turn is pending
  releaseGate();
  await sendPromise;
  expect(c.error).toBeNull(); // stale turn's failure is not the new thread's error
  expect(c.streaming).toBe(false);
});

it("discards a superseded rehydration when opens race", async () => {
  const resolvers = new Map<string, (m: ChatMessage[]) => void>();
  const loadFn = (id: string) =>
    new Promise<ChatMessage[]>((resolve) => resolvers.set(id, resolve));
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn: scripted().runFn, loadFn });
  const openA = c.openThread("A");
  const openB = c.openThread("B");
  resolvers.get("B")!([{ id: "b1", role: "user", content: "from B" }]);
  resolvers.get("A")!([{ id: "a1", role: "user", content: "from A" }]);
  await Promise.all([openA, openB]);
  expect(c.threadId).toBe("B");
  expect(c.messages).toEqual([{ id: "b1", role: "user", content: "from B" }]); // A discarded
});

it("exposes loading while a rehydration is pending", async () => {
  let releaseLoad!: (m: ChatMessage[]) => void;
  const loadFn = () =>
    new Promise<ChatMessage[]>((resolve) => (releaseLoad = resolve));
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn: scripted().runFn, loadFn });
  expect(c.loading).toBe(false);
  const opening = c.openThread("t9");
  expect(c.loading).toBe(true); // gated rehydration in flight
  releaseLoad([{ id: "u1", role: "user", content: "old" }]);
  await opening;
  expect(c.loading).toBe(false);
});

it("a superseded open's settle does not clear the winner's loading", async () => {
  const resolvers = new Map<string, (m: ChatMessage[]) => void>();
  const loadFn = (id: string) =>
    new Promise<ChatMessage[]>((resolve) => resolvers.set(id, resolve));
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn: scripted().runFn, loadFn });
  const openA = c.openThread("A");
  const openB = c.openThread("B");
  expect(c.loading).toBe(true);
  resolvers.get("A")!([{ id: "a1", role: "user", content: "from A" }]);
  await openA; // superseded open settles: B's loading must survive
  expect(c.loading).toBe(true);
  resolvers.get("B")!([{ id: "b1", role: "user", content: "from B" }]);
  await openB;
  expect(c.loading).toBe(false);
});

it("clears loading when the rehydration load rejects", async () => {
  const loadFn = async (): Promise<ChatMessage[]> => {
    throw new Error("down");
  };
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn: scripted().runFn, loadFn });
  await expect(c.openThread("t9")).rejects.toThrow("down");
  expect(c.loading).toBe(false);
});

it("send() during rehydration is a no-op", async () => {
  let releaseLoad!: (m: ChatMessage[]) => void;
  const loadFn = () =>
    new Promise<ChatMessage[]>((resolve) => (releaseLoad = resolve));
  const { runFn, calls } = scripted();
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn, loadFn });
  const opening = c.openThread("t9");
  await c.send("hi"); // thread still rehydrating: must not ship a run
  expect(calls).toHaveLength(0);
  expect(c.messages).toEqual([]);
  releaseLoad([{ id: "u1", role: "user", content: "old" }]);
  await opening;
  expect(c.threadId).toBe("t9");
  expect(c.messages).toHaveLength(1);
});

it("unblocks interaction at RUN_FINISHED, not at stream close (server-side titling window)", async () => {
  // Reproduces the reviewer's live probe: the backend holds the SSE response
  // open ~1 title-model round-trip PAST RUN_FINISHED. Approvals must not be
  // dropped, and approval-cards must not go permanently dead, during that
  // window.
  const interrupt = { id: "i1", toolCallId: "c1" };
  let releaseGate!: () => void;
  const gate = new Promise<void>((resolve) => (releaseGate = resolve));
  let reachedGate!: () => void;
  const atGate = new Promise<void>((resolve) => (reachedGate = resolve));
  async function* runFn(): AsyncGenerator<AgUiEvent> {
    yield { type: "RUN_STARTED" };
    yield {
      type: "TOOL_CALL_START",
      toolCallId: "c1",
      toolCallName: "ha_call_service",
      parentMessageId: "a1",
    };
    yield { type: "TOOL_CALL_END", toolCallId: "c1" };
    yield { type: "RUN_FINISHED", outcome: { type: "interrupt", interrupts: [interrupt] } };
    // By the time the generator resumes here, the consumer has already
    // folded RUN_FINISHED (for-await only resumes the producer after the
    // loop body for the prior value has run).
    reachedGate();
    await gate; // simulates the open titling window: stream stays open
    // Any events the old, superseded turn produces after a newer turn has
    // started must never fold into shared state.
    yield { type: "TEXT_MESSAGE_CONTENT", messageId: "ghost", delta: "leaked" };
    yield { type: "RUN_FINISHED" };
  }
  const host = new FakeHost();
  let finished = 0;
  host.addEventListener("turn-finished", () => finished++);
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  const sendPromise = c.send("turn it off");
  await atGate;

  // The interaction must unblock right at RUN_FINISHED, well before the
  // stream closes (the gate is still held).
  expect(c.streaming).toBe(false);
  expect(c.pendingInterrupts).toEqual([interrupt]);
  expect(finished).toBe(0); // stream hasn't closed yet: no turn-finished

  // The approval click must not be dropped by a stale `streaming` guard.
  const turn2 = scripted(
    { type: "RUN_STARTED" },
    { type: "TOOL_CALL_RESULT", messageId: "r1", toolCallId: "c1", content: "done" },
    { type: "RUN_FINISHED", outcome: { type: "success" } },
  );
  c.setRunFnForTests(turn2.runFn);
  await c.resolveInterrupt("i1", true);
  expect(turn2.calls).toHaveLength(1); // resume run actually started
  expect(c.pendingInterrupts).toEqual([]);
  expect(finished).toBe(1); // resume turn's own clean finish fired turn-finished

  // Now let the old turn's stream finally close.
  releaseGate();
  await sendPromise;
  expect(c.messages.some((m) => m.id === "ghost")).toBe(false); // no leaked fold
  expect(c.streaming).toBe(false); // resume turn's state is not clobbered
  expect(finished).toBe(1); // old turn's belated close must not double-fire
});
