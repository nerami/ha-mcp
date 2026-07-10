import { describe, expect, it } from "vitest";
import { applyTheme, resolveTheme } from "../src/theme";

describe("resolveTheme", () => {
  it("stored value wins over OS preference", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });
  it("falls back to OS preference when nothing stored", () => {
    expect(resolveTheme(null, true)).toBe("dark");
    expect(resolveTheme(null, false)).toBe("light");
  });
  it("ignores garbage stored values", () => {
    expect(resolveTheme("purple", false)).toBe("light");
  });
});

describe("applyTheme", () => {
  it("stamps data-theme on <html> and persists", () => {
    applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("concierge-theme")).toBe("dark");
  });
});
