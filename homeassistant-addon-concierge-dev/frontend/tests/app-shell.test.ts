import { expect, it } from "vitest";
import "../src/components/thread-sidebar";
import "../src/components/chat-panel";
import type { ThreadSidebar } from "../src/components/thread-sidebar";
import type { ChatPanel } from "../src/components/chat-panel";

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
    yield { type: "TOOL_CALL_END", toolCallId: "c1" } as const;
    yield {
      type: "RUN_FINISHED",
      outcome: { type: "interrupt", interrupts: [{ id: "i1", toolCallId: "c1" }] },
    } as const;
  });
  await el.controller.openThread(null);
  await el.controller.send("turn off the lights");
  await el.updateComplete;
  expect(el.shadowRoot!.querySelector("approval-card")).not.toBeNull();
  expect(el.shadowRoot!.querySelector('[aria-live="polite"]')).not.toBeNull();
  el.remove();
});
