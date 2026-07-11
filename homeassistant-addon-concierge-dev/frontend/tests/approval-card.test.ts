import { expect, it } from "vitest";
import "../src/components/approval-card";
import type { ApprovalCard } from "../src/components/approval-card";

async function mount() {
  const el = document.createElement("approval-card") as ApprovalCard;
  el.interrupt = { id: "i1", toolCallId: "c1" };
  el.toolName = "ha_call_service";
  el.toolArgs = '{"domain":"light","service":"turn_off"}';
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

it("shows the tool name and args", async () => {
  const el = await mount();
  const text = el.shadowRoot!.textContent ?? "";
  expect(text).toContain("ha_call_service");
  expect(text).toContain("turn_off");
  el.remove();
});

it("approve dispatches resolve-interrupt with approved=true and disables", async () => {
  const el = await mount();
  const seen: Array<{ interruptId: string; approved: boolean }> = [];
  el.addEventListener("resolve-interrupt", (e) =>
    seen.push((e as CustomEvent).detail),
  );
  const approve = el.shadowRoot!.querySelector<HTMLButtonElement>("button.approve")!;
  approve.click();
  await el.updateComplete;
  expect(seen).toEqual([{ interruptId: "i1", approved: true }]);
  expect(approve.disabled).toBe(true);
  el.remove();
});

it("deny dispatches approved=false", async () => {
  const el = await mount();
  const seen: Array<{ approved: boolean }> = [];
  el.addEventListener("resolve-interrupt", (e) =>
    seen.push((e as CustomEvent).detail),
  );
  el.shadowRoot!.querySelector<HTMLButtonElement>("button.deny")!.click();
  await el.updateComplete;
  expect(seen[0]!.approved).toBe(false);
  el.remove();
});
