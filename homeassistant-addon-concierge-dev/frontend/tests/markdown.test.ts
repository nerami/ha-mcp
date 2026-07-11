import { expect, it } from "vitest";
import { renderMarkdown } from "../src/markdown";

it("renders basic markdown", () => {
  const html = renderMarkdown("**bold** and `code`");
  expect(html).toContain("<strong>bold</strong>");
  expect(html).toContain("<code>code</code>");
});

it("strips script tags and event handlers", () => {
  const html = renderMarkdown('hi <script>alert(1)</script> <img src=x onerror="alert(1)">');
  expect(html).not.toContain("<script");
  expect(html).not.toContain("onerror");
});

it("neutralizes javascript: links", () => {
  const html = renderMarkdown("[x](javascript:alert(1))");
  expect(html).not.toContain("javascript:");
});
