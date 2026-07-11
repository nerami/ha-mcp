import { afterEach, beforeEach, expect, it, vi } from "vitest";
import "../src/components/concierge-app";
import type { ConciergeApp } from "../src/components/concierge-app";
import type { ChatPanel } from "../src/components/chat-panel";
import type { ThreadSidebar } from "../src/components/thread-sidebar";

beforeEach(() => {
  // The real ThreadsController's initial refresh fetches ./threads on
  // connect; stub it for determinism (it captures errors, never throws).
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json([])),
  );
  document.documentElement.setAttribute("data-theme", "light");
});

afterEach(() => {
  document.querySelectorAll("concierge-app").forEach((e) => e.remove());
  vi.unstubAllGlobals();
});

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

async function mount() {
  const app = document.createElement("concierge-app") as ConciergeApp;
  document.body.appendChild(app);
  await app.updateComplete;
  const panel = app.shadowRoot!.querySelector("chat-panel") as ChatPanel;
  const sidebar = app.shadowRoot!.querySelector(
    "thread-sidebar",
  ) as ThreadSidebar;
  // Instance-method spies shadow the prototype methods; installed after
  // mount, so firstUpdated's initial openThread(null) already ran for real.
  const openThread = vi.fn(async (_id: string | null) => {});
  panel.openThread = openThread;
  const refresh = vi.fn(async () => {});
  const remove = vi.fn(async (_id: string) => {});
  app.threads.refresh = refresh;
  app.threads.remove = remove;
  return { app, panel, sidebar, openThread, refresh, remove };
}

it("select-thread opens the thread in the chat panel", async () => {
  const { sidebar, openThread } = await mount();
  sidebar.dispatchEvent(
    new CustomEvent("select-thread", { detail: { id: "tX" } }),
  );
  await flush();
  expect(openThread).toHaveBeenCalledWith("tX");
});

it("new-thread opens a fresh thread", async () => {
  const { sidebar, openThread } = await mount();
  sidebar.dispatchEvent(new CustomEvent("new-thread"));
  await flush();
  expect(openThread).toHaveBeenCalledWith(null);
});

it("deleting the ACTIVE thread removes it and resets to a new chat", async () => {
  const { sidebar, openThread, remove } = await mount();
  sidebar.dispatchEvent(
    new CustomEvent("select-thread", { detail: { id: "t1" } }),
  );
  await flush();
  sidebar.dispatchEvent(
    new CustomEvent("delete-thread", { detail: { id: "t1" } }),
  );
  await flush();
  expect(remove).toHaveBeenCalledWith("t1");
  expect(openThread.mock.calls).toEqual([["t1"], [null]]);
});

it("deleting a NON-active thread removes it without resetting the chat", async () => {
  const { sidebar, openThread, remove } = await mount();
  sidebar.dispatchEvent(
    new CustomEvent("select-thread", { detail: { id: "t1" } }),
  );
  await flush();
  sidebar.dispatchEvent(
    new CustomEvent("delete-thread", { detail: { id: "t2" } }),
  );
  await flush();
  expect(remove).toHaveBeenCalledWith("t2");
  expect(openThread.mock.calls).toEqual([["t1"]]); // no reset
});

it("turn-finished on the chat panel refreshes the thread list", async () => {
  const { panel, refresh } = await mount();
  panel.dispatchEvent(new CustomEvent("turn-finished"));
  await flush();
  expect(refresh).toHaveBeenCalledTimes(1);
});

it("theme toggle flips data-theme on the document root", async () => {
  const { app } = await mount();
  const toggle = app.shadowRoot!.querySelector<HTMLButtonElement>(
    "button.theme-toggle",
  )!;
  toggle.click();
  expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  toggle.click();
  expect(document.documentElement.getAttribute("data-theme")).toBe("light");
});
