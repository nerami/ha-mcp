import { expect, it, vi } from "vitest";
import "../src/components/thread-sidebar";
import "../src/components/chat-panel";
import type { ThreadSidebar } from "../src/components/thread-sidebar";
import type { ChatPanel } from "../src/components/chat-panel";
import type { ApprovalCard } from "../src/components/approval-card";

it("sidebar lists threads and emits select/new/delete", async () => {
  const el = document.createElement("thread-sidebar") as ThreadSidebar;
  el.threads = [
    { id: "t1", title: "Lights" },
    { id: "t2", title: null },
  ];
  document.body.appendChild(el);
  await el.updateComplete;
  const text = el.shadowRoot!.textContent ?? "";
  expect(text).toContain("Lights");
  expect(text).toContain("Untitled");

  const events: string[] = [];
  el.addEventListener("new-thread", () => events.push("new"));
  el.addEventListener("select-thread", (e) =>
    events.push(`select:${(e as CustomEvent).detail.id}`),
  );
  el.shadowRoot!.querySelector<HTMLButtonElement>("button.new-thread")!.click();
  el.shadowRoot!.querySelector<HTMLButtonElement>("button.thread")!.click();
  expect(events).toEqual(["new", "select:t1"]);
  el.remove();
});

it("chat panel renders composer, streams a turn, shows approval card on interrupt", async () => {
  const el = document.createElement("chat-panel") as ChatPanel;
  document.body.appendChild(el);
  // scripted run: gated tool -> interrupt
  el.controller.setRunFnForTests(async function* () {
    yield { type: "RUN_STARTED" } as const;
    yield {
      type: "TOOL_CALL_START",
      toolCallId: "c1",
      toolCallName: "ha_call_service",
      parentMessageId: "a1",
    } as const;
    yield {
      type: "TOOL_CALL_ARGS",
      toolCallId: "c1",
      delta: '{"domain":"light"}',
    } as const;
    yield { type: "TOOL_CALL_END", toolCallId: "c1" } as const;
    yield {
      type: "RUN_FINISHED",
      outcome: { type: "interrupt", interrupts: [{ id: "i1", toolCallId: "c1" }] },
    } as const;
  });
  await el.controller.openThread(null);
  await el.controller.send("turn off the lights");
  await el.updateComplete;
  const card = el.shadowRoot!.querySelector("approval-card") as ApprovalCard;
  expect(card).not.toBeNull();
  // Derivation: toolName/toolArgs come from the assistant message's matching
  // toolCalls entry, looked up via interrupt.toolCallId.
  expect(card.toolName).toBe("ha_call_service");
  expect(card.toolArgs).toContain("domain");
  expect(el.shadowRoot!.querySelector('[aria-live="polite"]')).not.toBeNull();
  el.remove();
});

it("shows a thinking indicator during dead air, hides once output arrives", async () => {
  const el = document.createElement("chat-panel") as ChatPanel;
  document.body.appendChild(el);
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  // Hold the turn open with no assistant output yet — the "thinking" window.
  el.controller.setRunFnForTests(async function* () {
    yield { type: "RUN_STARTED" } as const;
    await gate;
    yield { type: "TEXT_MESSAGE_START", messageId: "a1" } as const;
    yield { type: "TEXT_MESSAGE_CONTENT", messageId: "a1", delta: "Hi!" } as const;
    yield { type: "RUN_FINISHED" } as const;
  });
  await el.controller.openThread(null);
  const sending = el.controller.send("hello"); // paused at the gate, do not await
  await el.updateComplete;
  // Dead air: streaming, only the user message present -> indicator visible.
  expect(el.shadowRoot!.querySelector(".thinking")).not.toBeNull();
  expect(el.shadowRoot!.querySelector('[role="status"]')).not.toBeNull();

  release();
  await sending;
  await el.updateComplete;
  // Assistant output has arrived and the turn finished -> indicator gone.
  expect(el.shadowRoot!.querySelector(".thinking")).toBeNull();
  expect(
    el.controller.messages.some(
      (m) => m.role === "assistant" && m.content.includes("Hi!"),
    ),
  ).toBe(true);
  el.remove();
});

it("composer is gated while a thread rehydrates: no clear, no run", async () => {
  // Gate the default loadFn (getThreadMessages) at the fetch layer.
  let releaseLoad!: (r: Response) => void;
  const gated = new Promise<Response>((resolve) => (releaseLoad = resolve));
  vi.stubGlobal("fetch", vi.fn(() => gated));
  try {
    const el = document.createElement("chat-panel") as ChatPanel;
    document.body.appendChild(el);
    const runFn = vi.fn(async function* () {
      yield { type: "RUN_STARTED" } as const;
      yield { type: "RUN_FINISHED" } as const;
    });
    el.controller.setRunFnForTests(runFn);

    const opening = el.openThread("t9");
    await el.updateComplete;
    const area = el.shadowRoot!.querySelector("textarea")!;
    const send = el.shadowRoot!.querySelector<HTMLButtonElement>(
      'button[type="submit"]',
    )!;
    expect(el.controller.loading).toBe(true);
    expect(area.disabled).toBe(true);
    expect(send.disabled).toBe(true);

    // Submitting while gated must leave the draft intact and ship no run.
    area.value = "turn off the lights";
    el.shadowRoot!
      .querySelector("form")!
      .dispatchEvent(new Event("submit", { cancelable: true }));
    expect(area.value).toBe("turn off the lights");
    expect(runFn).not.toHaveBeenCalled();

    releaseLoad(Response.json([]));
    await opening;
    await el.updateComplete;
    expect(el.controller.loading).toBe(false);
    expect(area.disabled).toBe(false);
    el.remove();
  } finally {
    vi.unstubAllGlobals();
  }
});
