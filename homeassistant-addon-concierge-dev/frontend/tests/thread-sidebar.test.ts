import { afterEach, expect, it } from "vitest";
import "../src/components/thread-sidebar";
import type { ThreadSidebar } from "../src/components/thread-sidebar";
import type { ThreadMeta } from "../src/agui/api";

afterEach(() => {
  document.querySelectorAll("thread-sidebar").forEach((e) => e.remove());
});

async function mount(threads: ThreadMeta[]): Promise<ThreadSidebar> {
  const el = document.createElement("thread-sidebar") as ThreadSidebar;
  el.threads = threads;
  document.body.appendChild(el);
  await el.updateComplete;
  return el;
}

const q = <T extends Element>(el: ThreadSidebar, sel: string): T | null =>
  el.renderRoot.querySelector<T>(sel);

it("clicking Rename reveals a pre-filled input", async () => {
  const el = await mount([{ id: "t1", title: "Hello" }]);
  expect(q<HTMLInputElement>(el, "input.rename-input")).toBeNull();

  q<HTMLButtonElement>(el, "button.rename")!.click();
  await el.updateComplete;

  const input = q<HTMLInputElement>(el, "input.rename-input");
  expect(input).not.toBeNull();
  expect(input!.value).toBe("Hello");
});

it("submitting a new title with Enter emits rename-thread with the new value", async () => {
  const el = await mount([{ id: "t1", title: "Hello" }]);
  q<HTMLButtonElement>(el, "button.rename")!.click();
  await el.updateComplete;

  const input = q<HTMLInputElement>(el, "input.rename-input")!;
  input.value = "Renamed";
  input.dispatchEvent(new Event("input"));

  let detail: { id: string; title: string } | undefined;
  el.addEventListener("rename-thread", (e) => {
    detail = (e as CustomEvent).detail;
  });
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
  await el.updateComplete;

  expect(detail).toEqual({ id: "t1", title: "Renamed" });
  // Input closes back into the read-only row after confirming.
  expect(q<HTMLInputElement>(el, "input.rename-input")).toBeNull();
});

it("the Save button also confirms the rename", async () => {
  const el = await mount([{ id: "t1", title: "Hello" }]);
  q<HTMLButtonElement>(el, "button.rename")!.click();
  await el.updateComplete;

  const input = q<HTMLInputElement>(el, "input.rename-input")!;
  input.value = "Via save";
  input.dispatchEvent(new Event("input"));

  let detail: { id: string; title: string } | undefined;
  el.addEventListener("rename-thread", (e) => {
    detail = (e as CustomEvent).detail;
  });
  q<HTMLButtonElement>(el, "button.save-rename")!.click();
  await el.updateComplete;

  expect(detail).toEqual({ id: "t1", title: "Via save" });
});

it("an empty / whitespace title is not submitted", async () => {
  const el = await mount([{ id: "t1", title: "Hello" }]);
  q<HTMLButtonElement>(el, "button.rename")!.click();
  await el.updateComplete;

  const input = q<HTMLInputElement>(el, "input.rename-input")!;
  input.value = "   ";
  input.dispatchEvent(new Event("input"));

  let emitted = false;
  el.addEventListener("rename-thread", () => {
    emitted = true;
  });
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
  await el.updateComplete;

  expect(emitted).toBe(false);
  // Whitespace-only confirm is discarded; edit mode closes with no change.
  expect(q<HTMLInputElement>(el, "input.rename-input")).toBeNull();
});

it("Escape cancels the edit without emitting", async () => {
  const el = await mount([{ id: "t1", title: "Hello" }]);
  q<HTMLButtonElement>(el, "button.rename")!.click();
  await el.updateComplete;

  const input = q<HTMLInputElement>(el, "input.rename-input")!;
  input.value = "Discarded";
  input.dispatchEvent(new Event("input"));

  let emitted = false;
  el.addEventListener("rename-thread", () => {
    emitted = true;
  });
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  await el.updateComplete;

  expect(emitted).toBe(false);
  expect(q<HTMLInputElement>(el, "input.rename-input")).toBeNull();
  // Original title is still shown.
  expect(q<HTMLButtonElement>(el, "button.thread")!.textContent?.trim()).toBe(
    "Hello",
  );
});

it("editing one row does not trigger select-thread on that row", async () => {
  const el = await mount([{ id: "t1", title: "Hello" }]);
  let selected = false;
  el.addEventListener("select-thread", () => {
    selected = true;
  });

  q<HTMLButtonElement>(el, "button.rename")!.click();
  await el.updateComplete;
  const input = q<HTMLInputElement>(el, "input.rename-input")!;
  input.value = "New";
  input.dispatchEvent(new Event("input"));
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
  await el.updateComplete;

  expect(selected).toBe(false);
});
