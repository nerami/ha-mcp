import { expect, it } from "vitest";
import "../src/components/tool-call-card";
import type { ToolCallCard } from "../src/components/tool-call-card";

it("shows the tool name and pretty args when expanded", async () => {
  const el = document.createElement("tool-call-card") as ToolCallCard;
  el.call = {
    id: "c1",
    type: "function",
    function: { name: "ha_call_service", arguments: '{"domain":"light"}' },
  };
  el.result = '{"success": true}';
  document.body.appendChild(el);
  await el.updateComplete;
  const text = el.shadowRoot!.textContent ?? "";
  expect(text).toContain("ha_call_service");
  expect(text).toContain('"domain"');
  expect(text).toContain("success");
  el.remove();
});

it("tolerates non-JSON args", async () => {
  const el = document.createElement("tool-call-card") as ToolCallCard;
  el.call = {
    id: "c1",
    type: "function",
    function: { name: "t", arguments: "not-json{" },
  };
  document.body.appendChild(el);
  await el.updateComplete;
  expect(el.shadowRoot!.textContent).toContain("not-json{");
  el.remove();
});
