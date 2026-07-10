import { describe, expect, it } from "vitest";
import "../src/components/concierge-app";

describe("<concierge-app>", () => {
  it("renders the shell landmarks", async () => {
    const el = document.createElement("concierge-app");
    document.body.appendChild(el);
    await (el as HTMLElement & { updateComplete: Promise<boolean> })
      .updateComplete;
    const root = el.shadowRoot!;
    expect(root.querySelector("main")).not.toBeNull();
    el.remove();
  });
});
