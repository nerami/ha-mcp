import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({ gfm: true, breaks: true, async: false });

/** Markdown -> sanitized HTML. The ONLY approved path for model output. */
export function renderMarkdown(md: string): string {
  const raw = marked.parse(md, { async: false }) as string;
  let sanitized = DOMPurify.sanitize(raw);

  // Fallback: if DOMPurify didn't remove script tags (happy-dom issue),
  // use regex-based sanitization
  if (sanitized.includes("<script")) {
    // Remove all script tags and their content
    sanitized = sanitized.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "");
    // Remove event handler attributes
    sanitized = sanitized.replace(/\s+(on\w+)\s*=\s*["'][^"']*["']/gi, "");
    sanitized = sanitized.replace(/\s+(on\w+)\s*=\s*[^\s>]*/gi, "");
  }

  // Handle javascript: URLs
  sanitized = sanitized.replace(/href\s*=\s*["']?javascript:/gi, 'href="');

  return sanitized;
}
