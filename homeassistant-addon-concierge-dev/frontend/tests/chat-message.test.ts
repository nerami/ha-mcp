import { expect, it } from "vitest";
import "../src/components/chat-message";
import type { ChatMessageEl } from "../src/components/chat-message";

async function mount(message: object, results?: Map<string, string>) {
  const el = document.createElement("chat-message") as ChatMessageEl;
  el.message = message as never;
  if (results) el.results = results;
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

it("renders a user message as text", async () => {
  const el = await mount({ id: "u1", role: "user", content: "<b>hi</b>" });
  expect(el.shadowRoot!.textContent).toContain("<b>hi</b>"); // literal, not HTML
  el.remove();
});

it("renders assistant markdown sanitized", async () => {
  const el = await mount({
    id: "a1",
    role: "assistant",
    content: "**bold** <script>alert(1)</script>",
  });
  expect(el.shadowRoot!.querySelector("strong")).not.toBeNull();
  expect(el.shadowRoot!.innerHTML).not.toContain("<script");
  el.remove();
});

it("renders a tool-call card with its joined result", async () => {
  const el = await mount(
    {
      id: "a1",
      role: "assistant",
      content: "",
      toolCalls: [
        { id: "c1", type: "function", function: { name: "ha_search", arguments: "{}" } },
      ],
    },
    new Map([["c1", '{"ok":true}']]),
  );
  const card = el.shadowRoot!.querySelector("tool-call-card");
  expect(card).not.toBeNull();
  el.remove();
});
