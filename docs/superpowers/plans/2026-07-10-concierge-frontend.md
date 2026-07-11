# Concierge Frontend Implementation Plan (Plan 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Concierge add-on's chat frontend: a Lit + TypeScript single-page app (Vite → static bundle, served by the existing FastAPI backend) that speaks the AG-UI protocol over SSE — streaming chat, tool-call cards, human-in-the-loop approval, and a thread sidebar — styled with HA design tokens.

**Architecture:** A Vite-built SPA at `homeassistant-addon-concierge-dev/frontend/` (tooled like the repo's `site/`: npm + TS + eslint; runtime deps are Lit + marked + dompurify only). Framework-free transport modules (`src/agui/`) hand-parse the AG-UI SSE stream; Lit `ReactiveController`s (`src/state/`) own turn/thread state; Lit components render. The backend gains one addition: traversal-safe static/SPA serving behind a `static_dir` setting.

**Tech Stack:** Lit ^3.3.3 · TypeScript ^6 (site/ parity) · Vite ^8.1.4 · Vitest ^4.1.10 + jsdom (test env; happy-dom was swapped out in Task 4 — DOMPurify silently fails to sanitize under happy-dom's incomplete DOM) · marked ^18.0.6 + dompurify ^3.4.11. NO React, NO `@ag-ui/client`/RxJS, NO CopilotKit.

**Contract authority:** `docs/superpowers/notes/2026-07-10-backend-handoff.md` (verified wire contract). Spec: `docs/superpowers/specs/2026-07-09-concierge-addon-design.md` §6-7.

## Global Constraints

- **Relative URLs everywhere.** Supervisor ingress serves the app under a dynamic prefix (`/api/hassio_ingress/<token>/`). Every API call uses relative paths (`./agui`, `./threads`, `./threads/${id}`) and `vite.config.ts` sets `base: ''`. An absolute `/agui` anywhere is a defect.
- **Wire contract (from the handoff notes — exact):**
  - `POST ./agui`, body `RunAgentInput`: `{threadId, runId, messages, tools: [], context: [], state: null, forwardedProps: null}`; `threadId`/`runId` are **client-generated** (`crypto.randomUUID()`). Response is always `text/event-stream`.
  - Events consumed: `RUN_STARTED`, `TEXT_MESSAGE_START|CONTENT|END`, `TOOL_CALL_START|ARGS|END`, `TOOL_CALL_RESULT`, `RUN_FINISHED` (may carry `outcome`), `RUN_ERROR` (`{message}`).
  - HITL: gated call → `RUN_FINISHED` with `outcome.type === "interrupt"`, `outcome.interrupts: [{id, toolCallId, ...}]`; NO `TOOL_CALL_RESULT` on that turn. Resume = new `RunAgentInput` with the thread's messages plus `resume: [{interruptId, status: "resolved", payload: {approved: true|false, editedArgs?, reason?}}]`. `approved` must be boolean `true` for approval — anything else is denial.
  - Mid-stream failure: HTTP 200 stream containing `RUN_ERROR`; `RUN_FINISHED` is NOT sent on that turn. Treat `RUN_ERROR` as turn-terminal.
  - The HTTP response stays open ~1 title-model round-trip past `RUN_FINISHED` (server-side titling) — act on events, never on stream close.
  - Rehydration: `GET ./threads` → `[{id, title, created_at, updated_at}]`; `GET ./threads/{id}` → raw AG-UI message dicts (camelCase: `toolCalls`, `toolCallId`) that round-trip into the next `RunAgentInput.messages`. `PATCH` renames (`{title}`), `DELETE` deletes (204).
  - Messages the FE builds: user `{id, role: "user", content}`; assistant `{id, role: "assistant", content, toolCalls?: [{id, type: "function", function: {name, arguments}}]}`; tool `{id, role: "tool", toolCallId, content}`.
- **Theme (spec §6.3 as amended):** `prefers-color-scheme` default + manual light/dark toggle persisted in `localStorage` key `concierge-theme`, applied as `data-theme` on `<html>` by an **inline anti-FOUC script in `index.html`** (the `settings_ui` pattern) before first paint. No `home-assistant-js-websocket` in v1.
- **A11y:** semantic landmarks (`<nav>`, `<main>`), the streaming message region is `aria-live="polite"`, all interactive controls are real `<button>`s with labels.
- **Markdown safety:** ALL assistant markdown goes through `renderMarkdown()` (marked → DOMPurify.sanitize) — never raw `unsafeHTML` of model output.
- **Dependencies are closed:** runtime = `lit`, `marked`, `dompurify`. Dev = `typescript`, `vite`, `vitest`, `happy-dom`, `@vitest/coverage-v8`, eslint 9 flat config + `typescript-eslint`, `prettier`. Adding anything else requires a documented reason in the task report.
- Backend edits in this plan are limited to static/SPA serving (Task 10): `concierge/config.py` (+`static_dir`), `concierge/web.py` (+static routes), `concierge/__main__.py` untouched, plus tests. Backend rules from Plan 1 still bind (ruff 88, mypy, uv project).
- FE commands run from `homeassistant-addon-concierge-dev/frontend/`; backend commands from `homeassistant-addon-concierge-dev/backend/`. Commits on `feat/concierge-addon`, never master. Conventional commits (`feat(concierge): …`).
- Lit decorators need `"experimentalDecorators": true` + `"useDefineForClassFields": false` in tsconfig.

---

### Task 1: Frontend scaffold (Vite + Lit + Vitest + eslint) with anti-FOUC theme boot

**Files:**
- Create: `homeassistant-addon-concierge-dev/frontend/package.json`
- Create: `homeassistant-addon-concierge-dev/frontend/tsconfig.json`
- Create: `homeassistant-addon-concierge-dev/frontend/vite.config.ts`
- Create: `homeassistant-addon-concierge-dev/frontend/eslint.config.js`
- Create: `homeassistant-addon-concierge-dev/frontend/index.html`
- Create: `homeassistant-addon-concierge-dev/frontend/src/main.ts`
- Create: `homeassistant-addon-concierge-dev/frontend/src/components/concierge-app.ts`
- Create: `homeassistant-addon-concierge-dev/frontend/src/theme.ts`
- Create: `homeassistant-addon-concierge-dev/frontend/src/tokens.css`
- Test: `homeassistant-addon-concierge-dev/frontend/tests/concierge-app.test.ts`, `tests/theme.test.ts`

**Interfaces:**
- Produces: a building, testable Vite project; `<concierge-app>` custom element; `theme.ts` exporting `resolveTheme(stored: string | null, prefersDark: boolean): "light" | "dark"` and `applyTheme(theme: "light" | "dark"): void` (sets `data-theme` on `document.documentElement` and persists); `tokens.css` defining the HA-flavored CSS custom properties for both `[data-theme="light"]` and `[data-theme="dark"]` (at minimum: `--c-bg`, `--c-surface`, `--c-text`, `--c-text-secondary`, `--c-primary` (#03a9f4 — HA blue), `--c-divider`, `--c-error`, `--c-radius`, `--c-font` (system stack)).

- [ ] **Step 1: Write `package.json`**

```json
{
  "name": "concierge-frontend",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "dompurify": "^3.4.11",
    "lit": "^3.3.3",
    "marked": "^18.0.6"
  },
  "devDependencies": {
    "@vitest/coverage-v8": "^4.1.10",
    "eslint": "^9.39.0",
    "happy-dom": "^20.10.6",
    "prettier": "^3.6.0",
    "typescript": "^6.0.3",
    "typescript-eslint": "^8.61.0",
    "vite": "^8.1.4",
    "vitest": "^4.1.10"
  }
}
```

(Version floors verified against the npm registry on 2026-07-10; TS stays on ^6 for `site/` parity — TS 7 is too fresh for this toolchain.)

- [ ] **Step 2: Write `tsconfig.json`, `vite.config.ts`, `eslint.config.js`**

`tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "experimentalDecorators": true,
    "useDefineForClassFields": false,
    "skipLibCheck": true,
    "noEmit": true,
    "types": ["vitest/globals"]
  },
  "include": ["src", "tests", "vite.config.ts"]
}
```

`vite.config.ts`:

```typescript
/// <reference types="vitest/config" />
import { defineConfig } from "vite";

export default defineConfig({
  // Relative asset URLs: the app is served under Supervisor ingress's
  // dynamic path prefix, so absolute paths would 404.
  base: "",
  server: {
    // Dev-mode proxy to the backend (uv run python -m concierge).
    proxy: {
      "/agui": "http://127.0.0.1:8098",
      "/threads": "http://127.0.0.1:8098",
    },
  },
  test: {
    environment: "jsdom", // happy-dom breaks DOMPurify (Task 4 finding)
    globals: true,
    include: ["tests/**/*.test.ts"],
  },
});
```

`eslint.config.js` (flat config, eslint 9 — mirrors `site/`'s model):

```javascript
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist/", "node_modules/"] },
  ...tseslint.configs.recommended,
  {
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_" },
      ],
    },
  },
);
```

- [ ] **Step 3: Write `index.html` with the anti-FOUC inline script**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Concierge</title>
    <script>
      // Anti-FOUC (settings_ui pattern): resolve the theme and stamp
      // data-theme on <html> BEFORE first paint. localStorage choice wins;
      // otherwise follow the OS preference (matches HA default behavior).
      (function () {
        var stored = null;
        try {
          stored = localStorage.getItem("concierge-theme");
        } catch (e) {
          /* storage unavailable: fall through to media query */
        }
        var dark =
          stored === "dark" ||
          (stored !== "light" &&
            window.matchMedia("(prefers-color-scheme: dark)").matches);
        document.documentElement.setAttribute(
          "data-theme",
          dark ? "dark" : "light",
        );
      })();
    </script>
    <link rel="stylesheet" href="./src/tokens.css" />
    <script type="module" src="./src/main.ts"></script>
  </head>
  <body>
    <concierge-app></concierge-app>
  </body>
</html>
```

- [ ] **Step 4: Write the failing tests**

`tests/theme.test.ts`:

```typescript
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
```

`tests/concierge-app.test.ts`:

```typescript
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
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd homeassistant-addon-concierge-dev/frontend && npm install && npx vitest run`
Expected: FAIL — cannot resolve `../src/theme` / `../src/components/concierge-app`.

- [ ] **Step 6: Implement `src/theme.ts`, `src/tokens.css`, `src/components/concierge-app.ts`, `src/main.ts`**

`src/theme.ts`:

```typescript
export type Theme = "light" | "dark";

export function resolveTheme(stored: string | null, prefersDark: boolean): Theme {
  if (stored === "light" || stored === "dark") return stored;
  return prefersDark ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  try {
    localStorage.setItem("concierge-theme", theme);
  } catch {
    /* storage unavailable (private mode): theme still applies for session */
  }
}

export function currentTheme(): Theme {
  return document.documentElement.getAttribute("data-theme") === "dark"
    ? "dark"
    : "light";
}
```

`src/tokens.css`:

```css
/* HA-flavored design tokens. --c-primary is HA's brand blue. */
:root,
:root[data-theme="light"] {
  --c-bg: #fafafa;
  --c-surface: #ffffff;
  --c-text: #212121;
  --c-text-secondary: #727272;
  --c-primary: #03a9f4;
  --c-on-primary: #ffffff;
  --c-divider: rgba(0, 0, 0, 0.12);
  --c-error: #db4437;
  --c-warning: #ffa600;
  --c-radius: 12px;
  --c-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color-scheme: light;
}
:root[data-theme="dark"] {
  --c-bg: #111318;
  --c-surface: #1c1e24;
  --c-text: #e1e1e1;
  --c-text-secondary: #9b9b9b;
  --c-primary: #03a9f4;
  --c-on-primary: #ffffff;
  --c-divider: rgba(255, 255, 255, 0.12);
  --c-error: #ef5350;
  --c-warning: #ffb74d;
  color-scheme: dark;
}
html,
body {
  margin: 0;
  height: 100%;
  background: var(--c-bg);
  color: var(--c-text);
  font-family: var(--c-font);
}
```

`src/components/concierge-app.ts` (v1 shell — grows in Task 9):

```typescript
import { LitElement, css, html } from "lit";
import { customElement } from "lit/decorators.js";

@customElement("concierge-app")
export class ConciergeApp extends LitElement {
  static styles = css`
    :host {
      display: flex;
      height: 100vh;
    }
    main {
      flex: 1;
      display: flex;
      flex-direction: column;
    }
  `;

  render() {
    return html`<main><h1>Concierge</h1></main>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "concierge-app": ConciergeApp;
  }
}
```

`src/main.ts`:

```typescript
import "./components/concierge-app";
```

- [ ] **Step 7: Verify tests pass + toolchain green**

Run: `npx vitest run` → all PASS. Then `npm run lint`, `npm run typecheck`, `npm run build` (produces `dist/` with relative asset URLs — grep `dist/index.html` for `src="./` to confirm `base: ""` took effect).

- [ ] **Step 8: Commit**

```bash
git add homeassistant-addon-concierge-dev/frontend
git commit -m "feat(concierge): frontend scaffold with Lit, Vite, and anti-FOUC theming"
```

(Confirm `dist/` and `node_modules/` are not staged — the repo root `.gitignore` covers `node_modules/`; add a `frontend/.gitignore` with `dist/` and `node_modules/` if anything shows up in `git status`.)

---

### Task 2: AG-UI SSE parser (framework-free)

**Files:**
- Create: `src/agui/events.ts`
- Create: `src/agui/sse.ts`
- Test: `tests/sse.test.ts`

**Interfaces:**
- Produces: `events.ts` exporting the `AgUiEvent` discriminated union (typed subset: `RUN_STARTED`, `TEXT_MESSAGE_START/CONTENT/END`, `TOOL_CALL_START/ARGS/END`, `TOOL_CALL_RESULT`, `RUN_FINISHED` with `outcome?: {type: string; interrupts?: Interrupt[]}`, `RUN_ERROR` with `message: string`; `Interrupt = {id: string; toolCallId?: string; reason?: string; message?: string}`). The union is **closed** — a sibling `{type: string}` catch-all would defeat discriminant narrowing on every variant (verified with tsc); unknown runtime event types pass through the parser's cast and land in consumers' `switch` `default` branches, which is the forward-compat path. `sse.ts` exporting `async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<AgUiEvent>` — splits SSE frames on `\n\n`, handles frames split across chunks, multiple `data:` lines per frame (joined with `\n`), ignores comments/other fields, tolerates `\r\n`.

- [ ] **Step 1: Write the failing test**

`tests/sse.test.ts`:

```typescript
import { expect, it } from "vitest";
import { parseSse } from "../src/agui/sse";
import type { AgUiEvent } from "../src/agui/events";

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(enc.encode(c));
      controller.close();
    },
  });
}

async function collect(s: ReadableStream<Uint8Array>): Promise<AgUiEvent[]> {
  const out: AgUiEvent[] = [];
  for await (const ev of parseSse(s)) out.push(ev);
  return out;
}

it("parses complete frames", async () => {
  const events = await collect(
    streamOf(
      'data: {"type":"RUN_STARTED"}\n\n',
      'data: {"type":"TEXT_MESSAGE_CONTENT","messageId":"a1","delta":"Hi"}\n\n',
    ),
  );
  expect(events.map((e) => e.type)).toEqual([
    "RUN_STARTED",
    "TEXT_MESSAGE_CONTENT",
  ]);
});

it("reassembles a frame split across chunks", async () => {
  const events = await collect(
    streamOf('data: {"type":"RUN_ST', 'ARTED"}\n\ndata: {"type":"RUN_FINISHED"}\n\n'),
  );
  expect(events.map((e) => e.type)).toEqual(["RUN_STARTED", "RUN_FINISHED"]);
});

it("handles CRLF and ignores non-data lines", async () => {
  const events = await collect(
    streamOf(': comment\r\nevent: x\r\ndata: {"type":"RUN_ERROR","message":"boom"}\r\n\r\n'),
  );
  expect(events).toEqual([{ type: "RUN_ERROR", message: "boom" }]);
});

it("joins multi-data-line frames and skips malformed JSON", async () => {
  const events = await collect(
    streamOf('data: {"type":\ndata: "RUN_STARTED"}\n\n', "data: not-json\n\n"),
  );
  expect(events).toEqual([{ type: "RUN_STARTED" }]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/sse.test.ts` — FAIL (module not found).

- [ ] **Step 3: Implement `src/agui/events.ts` and `src/agui/sse.ts`**

`src/agui/events.ts`:

```typescript
export interface Interrupt {
  id: string;
  toolCallId?: string;
  reason?: string;
  message?: string;
}

export interface RunFinishedOutcome {
  type: string;
  interrupts?: Interrupt[];
}

export type AgUiEvent =
  | { type: "RUN_STARTED" }
  | { type: "TEXT_MESSAGE_START"; messageId: string; role?: string }
  | { type: "TEXT_MESSAGE_CONTENT"; messageId: string; delta: string }
  | { type: "TEXT_MESSAGE_END"; messageId: string }
  | {
      type: "TOOL_CALL_START";
      toolCallId: string;
      toolCallName: string;
      parentMessageId?: string;
    }
  | { type: "TOOL_CALL_ARGS"; toolCallId: string; delta: string }
  | { type: "TOOL_CALL_END"; toolCallId: string }
  | {
      type: "TOOL_CALL_RESULT";
      messageId: string;
      toolCallId: string;
      content: string;
    }
  | { type: "RUN_FINISHED"; outcome?: RunFinishedOutcome }
  | { type: "RUN_ERROR"; message: string };
// Deliberately CLOSED: a sibling `{type: string}` catch-all defeats
// discriminant narrowing on every variant. Unknown runtime event types pass
// through parseSse's cast and reach consumers' `default` branches.
```

`src/agui/sse.ts`:

```typescript
import type { AgUiEvent } from "./events";

/**
 * Parse an SSE byte stream into AG-UI events.
 *
 * Hand-rolled on purpose: EventSource is GET-only (AG-UI POSTs
 * RunAgentInput) and @ag-ui/client drags in RxJS. SSE framing is small:
 * frames are separated by a blank line; each frame's data is the
 * newline-join of its `data:` lines.
 */
export async function* parseSse(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<AgUiEvent> {
  const decoder = new TextDecoder();
  const reader = body.getReader();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      let sep;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).replace(/^ /, ""))
          .join("\n");
        if (!data) continue;
        try {
          yield JSON.parse(data) as AgUiEvent;
        } catch {
          // Malformed frame: skip rather than kill the stream.
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/sse.test.ts` — 4 PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
npm run lint && npm run typecheck
git add . && git commit -m "feat(concierge): hand-rolled AG-UI SSE parser"
```

---

### Task 3: API client (runs + threads, relative URLs)

**Files:**
- Create: `src/agui/api.ts`
- Test: `tests/api.test.ts`

**Interfaces:**
- Consumes: `parseSse` (Task 2).
- Produces: message types `ChatMessage` (`UserMessage {id, role: "user", content}`, `AssistantMessage {id, role: "assistant", content, toolCalls?}`, `ToolMessage {id, role: "tool", toolCallId, content}`); `ResumeEntry {interruptId, status: "resolved", payload: {approved: boolean, editedArgs?, reason?}}`; `buildRunInput(threadId, messages, resume?) -> RunAgentInput` (fills `runId` via `crypto.randomUUID()`, `tools: []`, `context: []`, `state: null`, `forwardedProps: null`); `postRun(input, fetchFn?) -> AsyncGenerator<AgUiEvent>` (POST `./agui`, throws `Error` on non-2xx); `listThreads(fetchFn?)`, `getThreadMessages(id, fetchFn?)`, `renameThread(id, title, fetchFn?)`, `deleteThread(id, fetchFn?)` — all relative paths, all taking an injectable `fetchFn = defaultFetch` test seam, where `defaultFetch` is a bound wrapper `(url, init) => fetch(url, init)` — a bare `fetch` default is an unbound reference and throws `Illegal invocation` in real browsers.

- [ ] **Step 1: Write the failing test**

`tests/api.test.ts`:

```typescript
import { expect, it } from "vitest";
import {
  buildRunInput,
  deleteThread,
  getThreadMessages,
  listThreads,
  postRun,
} from "../src/agui/api";

function sseResponse(bodyText: string): Response {
  return new Response(bodyText, {
    status: 200,
    headers: { "content-type": "text/event-stream" },
  });
}

it("buildRunInput fills protocol fields and generates a runId", () => {
  const input = buildRunInput("t1", [{ id: "u1", role: "user", content: "hi" }]);
  expect(input.threadId).toBe("t1");
  expect(input.runId).toMatch(/[0-9a-f-]{36}/);
  expect(input.tools).toEqual([]);
  expect(input.context).toEqual([]);
  expect(input.state).toBeNull();
  expect(input.forwardedProps).toBeNull();
  expect(input.resume).toBeUndefined();
});

it("buildRunInput carries resume entries when given", () => {
  const input = buildRunInput("t1", [], [
    { interruptId: "i1", status: "resolved", payload: { approved: true } },
  ]);
  expect(input.resume).toHaveLength(1);
});

it("postRun POSTs a relative ./agui URL and yields parsed events", async () => {
  const seen: { url: string; init: RequestInit }[] = [];
  const fetchFn = async (url: string | URL | Request, init?: RequestInit) => {
    seen.push({ url: String(url), init: init! });
    return sseResponse('data: {"type":"RUN_STARTED"}\n\ndata: {"type":"RUN_FINISHED"}\n\n');
  };
  const events = [];
  for await (const ev of postRun(buildRunInput("t1", []), fetchFn)) events.push(ev);
  expect(seen[0]!.url).toBe("./agui");
  expect(seen[0]!.init.method).toBe("POST");
  expect(events.map((e) => e.type)).toEqual(["RUN_STARTED", "RUN_FINISHED"]);
});

it("postRun throws on non-2xx", async () => {
  const fetchFn = async () => new Response("nope", { status: 422 });
  await expect(async () => {
    for await (const _ of postRun(buildRunInput("t1", []), fetchFn)) {
      /* drain */
    }
  }).rejects.toThrow(/422/);
});

it("thread CRUD uses relative URLs and parses JSON", async () => {
  const calls: string[] = [];
  const fetchFn = async (url: string | URL | Request, init?: RequestInit) => {
    calls.push(`${init?.method ?? "GET"} ${String(url)}`);
    if (String(url) === "./threads")
      return Response.json([{ id: "t1", title: "T" }]);
    if (init?.method === "DELETE") return new Response(null, { status: 204 });
    return Response.json([{ id: "u1", role: "user", content: "x" }]);
  };
  expect(await listThreads(fetchFn)).toEqual([{ id: "t1", title: "T" }]);
  expect(await getThreadMessages("t1", fetchFn)).toHaveLength(1);
  await deleteThread("t1", fetchFn);
  expect(calls).toEqual(["GET ./threads", "GET ./threads/t1", "DELETE ./threads/t1"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/api.test.ts` — FAIL (module not found).

- [ ] **Step 3: Implement `src/agui/api.ts`**

```typescript
import type { AgUiEvent } from "./events";
import { parseSse } from "./sse";

export interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: string };
}

export interface UserMessage {
  id: string;
  role: "user";
  content: string;
}
export interface AssistantMessage {
  id: string;
  role: "assistant";
  content: string;
  toolCalls?: ToolCall[];
}
export interface ToolMessage {
  id: string;
  role: "tool";
  toolCallId: string;
  content: string;
}
export type ChatMessage = UserMessage | AssistantMessage | ToolMessage;

export interface ResumeEntry {
  interruptId: string;
  status: "resolved";
  payload: { approved: boolean; editedArgs?: Record<string, unknown>; reason?: string };
}

export interface RunAgentInput {
  threadId: string;
  runId: string;
  messages: ChatMessage[];
  tools: unknown[];
  context: unknown[];
  state: null;
  forwardedProps: null;
  resume?: ResumeEntry[];
}

export interface ThreadMeta {
  id: string;
  title: string | null;
  created_at?: number;
  updated_at?: number;
}

export type FetchFn = (
  url: string,
  init?: RequestInit,
) => Promise<Response>;

// Bare `fetch` as a default parameter would be an unbound reference —
// browsers brand-check the receiver and throw "Illegal invocation".
const defaultFetch: FetchFn = (url, init) => fetch(url, init);

export function buildRunInput(
  threadId: string,
  messages: ChatMessage[],
  resume?: ResumeEntry[],
): RunAgentInput {
  const input: RunAgentInput = {
    threadId,
    runId: crypto.randomUUID(),
    messages,
    tools: [],
    context: [],
    state: null,
    forwardedProps: null,
  };
  if (resume) input.resume = resume;
  return input;
}

// All URLs are RELATIVE: under Supervisor ingress the app lives beneath a
// dynamic path prefix, so "/agui" would escape it and 404.
export async function* postRun(
  input: RunAgentInput,
  fetchFn: FetchFn = defaultFetch,
): AsyncGenerator<AgUiEvent> {
  const resp = await fetchFn("./agui", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`run failed: HTTP ${resp.status}`);
  }
  yield* parseSse(resp.body);
}

async function json<T>(resp: Response, what: string): Promise<T> {
  if (!resp.ok) throw new Error(`${what} failed: HTTP ${resp.status}`);
  return (await resp.json()) as T;
}

export async function listThreads(
  fetchFn: FetchFn = defaultFetch,
): Promise<ThreadMeta[]> {
  return json(await fetchFn("./threads"), "list threads");
}

export async function getThreadMessages(
  id: string,
  fetchFn: FetchFn = defaultFetch,
): Promise<ChatMessage[]> {
  return json(await fetchFn(`./threads/${encodeURIComponent(id)}`), "get thread");
}

export async function renameThread(
  id: string,
  title: string,
  fetchFn: FetchFn = defaultFetch,
): Promise<void> {
  const resp = await fetchFn(`./threads/${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!resp.ok) throw new Error(`rename failed: HTTP ${resp.status}`);
}

export async function deleteThread(
  id: string,
  fetchFn: FetchFn = defaultFetch,
): Promise<void> {
  const resp = await fetchFn(`./threads/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!resp.ok) throw new Error(`delete failed: HTTP ${resp.status}`);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/api.test.ts` — 5 PASS.

- [ ] **Step 5: Lint, typecheck, commit**

```bash
npm run lint && npm run typecheck
git add . && git commit -m "feat(concierge): AG-UI api client with relative-path transport"
```

---

### Task 4: Markdown renderer (sanitized)

**Files:**
- Create: `src/markdown.ts`
- Test: `tests/markdown.test.ts`

**Interfaces:**
- Produces: `renderMarkdown(md: string): string` — marked (GFM, no raw-HTML passthrough concerns because output is always DOMPurify-sanitized) → sanitized HTML string, safe to bind via Lit's `unsafeHTML`.

- [ ] **Step 1: Write the failing test**

`tests/markdown.test.ts`:

```typescript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/markdown.test.ts` — FAIL (module not found).

- [ ] **Step 3: Implement `src/markdown.ts`**

```typescript
import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({ gfm: true, breaks: true, async: false });

/** Markdown -> sanitized HTML. The ONLY approved path for model output. */
export function renderMarkdown(md: string): string {
  const raw = marked.parse(md, { async: false }) as string;
  return DOMPurify.sanitize(raw);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/markdown.test.ts` — 3 PASS.
(If DOMPurify needs an explicit window in happy-dom — `DOMPurify.sanitize` returning empty — initialize with `DOMPurify(window)`; adapt minimally and note it.)

- [ ] **Step 5: Lint, typecheck, commit**

```bash
npm run lint && npm run typecheck
git add . && git commit -m "feat(concierge): sanitized markdown rendering"
```

---

### Task 5: Chat controller (turn state machine)

**Files:**
- Create: `src/state/chat-controller.ts`
- Test: `tests/chat-controller.test.ts`

**Interfaces:**
- Consumes: `postRun`, `buildRunInput`, `getThreadMessages`, message types, `ResumeEntry` (Task 3); `AgUiEvent`, `Interrupt` (Task 2).
- Produces: `ChatController implements ReactiveController` with:
  - `constructor(host: ReactiveControllerHost, opts?: {runFn?: typeof postRun; loadFn?: typeof getThreadMessages})` — injectable seams.
  - State (read by components): `threadId: string | null`, `messages: ChatMessage[]`, `streaming: boolean`, `pendingInterrupts: Interrupt[]`, `error: string | null`, and `toolCallsInFlight: Map<string, {name: string; args: string; result?: string}>`.
  - `async openThread(id: string | null)` — `null` = new thread (generates `threadId` via `crypto.randomUUID()`, empty messages); string = rehydrate via `loadFn`.
  - `async send(text: string)` — appends the user message locally, streams the run, folds events into state (mirrors the backend accumulator: `TEXT_MESSAGE_*` build/extend an assistant message; `TOOL_CALL_START/ARGS` build `toolCalls` on the assistant message keyed by `parentMessageId ?? toolCallId`; `TOOL_CALL_RESULT` appends a tool message), captures `RUN_FINISHED.outcome.interrupts` into `pendingInterrupts`, treats `RUN_ERROR` as turn-terminal (`error` set, `streaming` false). Calls `host.requestUpdate()` after every event.
  - `async resolveInterrupt(interruptId: string, approved: boolean, reason?: string)` — builds a resume `RunAgentInput` from the CURRENT `messages` + one `ResumeEntry` (`payload.approved` boolean), clears that interrupt, streams the continuation through the same event-folding path.
  - `dispose()` no-op hooks `hostConnected/hostDisconnected`.
  - Emits a `turn-finished` CustomEvent on the host element after any `RUN_FINISHED` — including interrupt outcomes, since the backend generates titles even for gated first turns — but NOT after `RUN_ERROR`. An epoch guard makes `openThread()` safe against an in-flight turn: bumping the epoch stops the stale turn's folds/side-effects immediately.

- [ ] **Step 1: Write the failing test**

`tests/chat-controller.test.ts` (a fake host + scripted event streams — no HTTP):

```typescript
import { expect, it } from "vitest";
import { ChatController } from "../src/state/chat-controller";
import type { AgUiEvent } from "../src/agui/events";
import type { RunAgentInput } from "../src/agui/api";

class FakeHost extends EventTarget {
  updates = 0;
  addController(): void {}
  removeController(): void {}
  requestUpdate(): void {
    this.updates++;
  }
  readonly updateComplete = Promise.resolve(true);
}

function scripted(...events: AgUiEvent[]) {
  const calls: RunAgentInput[] = [];
  async function* runFn(input: RunAgentInput) {
    calls.push(input);
    for (const ev of events) yield ev;
  }
  return { runFn, calls };
}

it("folds a plain text turn into messages", async () => {
  const { runFn } = scripted(
    { type: "RUN_STARTED" },
    { type: "TEXT_MESSAGE_START", messageId: "a1" },
    { type: "TEXT_MESSAGE_CONTENT", messageId: "a1", delta: "Hel" },
    { type: "TEXT_MESSAGE_CONTENT", messageId: "a1", delta: "lo" },
    { type: "TEXT_MESSAGE_END", messageId: "a1" },
    { type: "RUN_FINISHED" },
  );
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  await c.send("hi");
  expect(c.messages.at(0)).toMatchObject({ role: "user", content: "hi" });
  expect(c.messages.at(-1)).toMatchObject({ role: "assistant", content: "Hello" });
  expect(c.streaming).toBe(false);
  expect(c.error).toBeNull();
  expect(host.updates).toBeGreaterThan(2);
});

it("folds tool calls and results", async () => {
  const { runFn } = scripted(
    { type: "RUN_STARTED" },
    { type: "TOOL_CALL_START", toolCallId: "c1", toolCallName: "ha_search", parentMessageId: "a1" },
    { type: "TOOL_CALL_ARGS", toolCallId: "c1", delta: '{"query":"x"}' },
    { type: "TOOL_CALL_END", toolCallId: "c1" },
    { type: "TOOL_CALL_RESULT", messageId: "r1", toolCallId: "c1", content: "ok" },
    { type: "RUN_FINISHED" },
  );
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  await c.send("search");
  const assistant = c.messages.find((m) => m.role === "assistant");
  expect(assistant).toMatchObject({
    toolCalls: [{ id: "c1", function: { name: "ha_search", arguments: '{"query":"x"}' } }],
  });
  expect(c.messages.at(-1)).toMatchObject({ role: "tool", toolCallId: "c1", content: "ok" });
});

it("captures interrupts and resumes with approval", async () => {
  const interrupt = { id: "i1", toolCallId: "c1" };
  const turn1 = scripted(
    { type: "RUN_STARTED" },
    { type: "TOOL_CALL_START", toolCallId: "c1", toolCallName: "ha_call_service", parentMessageId: "a1" },
    { type: "TOOL_CALL_END", toolCallId: "c1" },
    { type: "RUN_FINISHED", outcome: { type: "interrupt", interrupts: [interrupt] } },
  );
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn: turn1.runFn });
  await c.openThread(null);
  await c.send("turn it off");
  expect(c.pendingInterrupts).toEqual([interrupt]);
  expect(c.streaming).toBe(false);

  const turn2 = scripted(
    { type: "RUN_STARTED" },
    { type: "TOOL_CALL_RESULT", messageId: "r1", toolCallId: "c1", content: "done" },
    { type: "RUN_FINISHED", outcome: { type: "success" } },
  );
  c.setRunFnForTests(turn2.runFn);
  await c.resolveInterrupt("i1", true);
  expect(turn2.calls[0]!.resume).toEqual([
    { interruptId: "i1", status: "resolved", payload: { approved: true } },
  ]);
  expect(turn2.calls[0]!.messages.length).toBeGreaterThan(0); // thread round-trip
  expect(c.pendingInterrupts).toEqual([]);
  expect(c.messages.at(-1)).toMatchObject({ role: "tool", content: "done" });
});

it("treats RUN_ERROR as turn-terminal", async () => {
  const { runFn } = scripted(
    { type: "RUN_STARTED" },
    { type: "TEXT_MESSAGE_CONTENT", messageId: "a1", delta: "partial" },
    { type: "RUN_ERROR", message: "boom" },
  );
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn });
  await c.openThread(null);
  await c.send("hi");
  expect(c.error).toBe("boom");
  expect(c.streaming).toBe(false);
  expect(c.messages.at(-1)).toMatchObject({ role: "assistant", content: "partial" });
});

it("rehydrates an existing thread", async () => {
  const loadFn = async () => [{ id: "u1", role: "user" as const, content: "old" }];
  const host = new FakeHost();
  const c = new ChatController(host as never, { runFn: scripted().runFn, loadFn });
  await c.openThread("t9");
  expect(c.threadId).toBe("t9");
  expect(c.messages).toHaveLength(1);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npx vitest run tests/chat-controller.test.ts` — FAIL (module not found).

- [ ] **Step 3: Implement `src/state/chat-controller.ts`**

```typescript
import type { ReactiveController, ReactiveControllerHost } from "lit";
import type { AgUiEvent, Interrupt } from "../agui/events";
import {
  buildRunInput,
  getThreadMessages,
  postRun,
  type AssistantMessage,
  type ChatMessage,
  type ResumeEntry,
  type RunAgentInput,
} from "../agui/api";

type RunFn = (input: RunAgentInput) => AsyncGenerator<AgUiEvent>;
type LoadFn = (id: string) => Promise<ChatMessage[]>;

type Host = ReactiveControllerHost & Partial<EventTarget>;

/** Owns one open thread: messages, streaming turn state, HITL interrupts. */
export class ChatController implements ReactiveController {
  threadId: string | null = null;
  messages: ChatMessage[] = [];
  streaming = false;
  pendingInterrupts: Interrupt[] = [];
  error: string | null = null;
  toolCallsInFlight = new Map<string, { name: string; args: string; result?: string }>();

  private runFn: RunFn;
  private loadFn: LoadFn;
  private host: Host;

  constructor(host: Host, opts: { runFn?: RunFn; loadFn?: LoadFn } = {}) {
    this.host = host;
    this.runFn = opts.runFn ?? postRun;
    this.loadFn = opts.loadFn ?? getThreadMessages;
    host.addController(this);
  }

  hostConnected(): void {}
  hostDisconnected(): void {}

  async openThread(id: string | null): Promise<void> {
    this.error = null;
    this.pendingInterrupts = [];
    this.toolCallsInFlight = new Map();
    if (id === null) {
      this.threadId = crypto.randomUUID();
      this.messages = [];
    } else {
      this.threadId = id;
      this.messages = await this.loadFn(id);
    }
    this.host.requestUpdate();
  }

  async send(text: string): Promise<void> {
    if (this.threadId === null || this.streaming) return;
    this.messages = [
      ...this.messages,
      { id: crypto.randomUUID(), role: "user", content: text },
    ];
    await this.runTurn(buildRunInput(this.threadId, this.messages));
  }

  async resolveInterrupt(
    interruptId: string,
    approved: boolean,
    reason?: string,
  ): Promise<void> {
    if (this.threadId === null || this.streaming) return;
    const entry: ResumeEntry = {
      interruptId,
      status: "resolved",
      payload: reason ? { approved, reason } : { approved },
    };
    this.pendingInterrupts = this.pendingInterrupts.filter(
      (i) => i.id !== interruptId,
    );
    await this.runTurn(buildRunInput(this.threadId, this.messages, [entry]));
  }

  private async runTurn(input: RunAgentInput): Promise<void> {
    this.streaming = true;
    this.error = null;
    this.host.requestUpdate();
    let finishedCleanly = false;
    try {
      for await (const ev of this.runFn(input)) {
        this.fold(ev);
        this.host.requestUpdate();
        if (ev.type === "RUN_ERROR") break; // turn-terminal per contract
        if (ev.type === "RUN_FINISHED") finishedCleanly = true;
      }
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    } finally {
      this.streaming = false;
      this.host.requestUpdate();
      if (finishedCleanly && this.host.dispatchEvent) {
        this.host.dispatchEvent(new CustomEvent("turn-finished"));
      }
    }
  }

  private assistant(messageId: string): AssistantMessage {
    const existing = this.messages.find(
      (m): m is AssistantMessage => m.role === "assistant" && m.id === messageId,
    );
    if (existing) return existing;
    const fresh: AssistantMessage = { id: messageId, role: "assistant", content: "" };
    this.messages = [...this.messages, fresh];
    return fresh;
  }

  private fold(ev: AgUiEvent): void {
    switch (ev.type) {
      case "TEXT_MESSAGE_START":
        this.assistant(ev.messageId);
        break;
      case "TEXT_MESSAGE_CONTENT": {
        const message = this.assistant(ev.messageId);
        message.content += ev.delta;
        this.messages = [...this.messages];
        break;
      }
      case "TOOL_CALL_START": {
        const parent = this.assistant(ev.parentMessageId ?? ev.toolCallId);
        parent.toolCalls = [
          ...(parent.toolCalls ?? []),
          { id: ev.toolCallId, type: "function", function: { name: ev.toolCallName, arguments: "" } },
        ];
        this.toolCallsInFlight.set(ev.toolCallId, { name: ev.toolCallName, args: "" });
        this.messages = [...this.messages];
        break;
      }
      case "TOOL_CALL_ARGS": {
        const call = this.messages
          .filter((m): m is AssistantMessage => m.role === "assistant")
          .flatMap((m) => m.toolCalls ?? [])
          .find((c) => c.id === ev.toolCallId);
        if (call) call.function.arguments += ev.delta;
        const inflight = this.toolCallsInFlight.get(ev.toolCallId);
        if (inflight) inflight.args += ev.delta;
        this.messages = [...this.messages];
        break;
      }
      case "TOOL_CALL_RESULT": {
        this.messages = [
          ...this.messages,
          { id: ev.messageId, role: "tool", toolCallId: ev.toolCallId, content: ev.content },
        ];
        const inflight = this.toolCallsInFlight.get(ev.toolCallId);
        if (inflight) inflight.result = ev.content;
        break;
      }
      case "RUN_FINISHED":
        if (ev.outcome?.type === "interrupt" && ev.outcome.interrupts) {
          this.pendingInterrupts = [...this.pendingInterrupts, ...ev.outcome.interrupts];
        }
        break;
      case "RUN_ERROR":
        this.error = ev.message;
        break;
      default:
        break; // forward-compat: ignore unknown events
    }
  }

  /** Test-only seam: components construct their own controller. */
  setRunFnForTests(runFn: RunFn): void {
    this.runFn = runFn;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run tests/chat-controller.test.ts` — 5 PASS.

- [ ] **Step 5: Lint, typecheck, full FE suite, commit**

```bash
npm run lint && npm run typecheck && npx vitest run
git add . && git commit -m "feat(concierge): chat controller turn state machine"
```

---

### Task 6: Threads controller

**Files:**
- Create: `src/state/threads-controller.ts`
- Test: `tests/threads-controller.test.ts`

**Interfaces:**
- Consumes: `listThreads`, `renameThread`, `deleteThread`, `ThreadMeta` (Task 3).
- Produces: `ThreadsController implements ReactiveController` with `threads: ThreadMeta[]`, `loading: boolean`, `async refresh()`, `async rename(id, title)` (optimistic update + refresh), `async remove(id)` (refresh after), all with injectable fns `{listFn?, renameFn?, deleteFn?}`; `hostConnected()` triggers an initial `refresh()`. Errors are captured to `error: string | null`, never thrown to the host.

- [ ] **Step 1: Write the failing test**

`tests/threads-controller.test.ts`:

```typescript
import { expect, it } from "vitest";
import { ThreadsController } from "../src/state/threads-controller";

class FakeHost {
  updates = 0;
  addController(): void {}
  removeController(): void {}
  requestUpdate(): void {
    this.updates++;
  }
  readonly updateComplete = Promise.resolve(true);
}

it("refresh loads threads newest-first as served", async () => {
  const listFn = async () => [
    { id: "t2", title: "B" },
    { id: "t1", title: null },
  ];
  const c = new ThreadsController(new FakeHost() as never, { listFn });
  await c.refresh();
  expect(c.threads.map((t) => t.id)).toEqual(["t2", "t1"]);
  expect(c.loading).toBe(false);
});

it("rename is optimistic then refreshes", async () => {
  let served = [{ id: "t1", title: "old" }];
  const listFn = async () => served;
  const renameFn = async (_id: string, title: string) => {
    served = [{ id: "t1", title }];
  };
  const c = new ThreadsController(new FakeHost() as never, { listFn, renameFn });
  await c.refresh();
  await c.rename("t1", "new");
  expect(c.threads[0]!.title).toBe("new");
});

it("remove deletes then refreshes", async () => {
  let served = [{ id: "t1", title: "x" }];
  const deleteFn = async () => {
    served = [];
  };
  const c = new ThreadsController(new FakeHost() as never, {
    listFn: async () => served,
    deleteFn,
  });
  await c.refresh();
  await c.remove("t1");
  expect(c.threads).toEqual([]);
});

it("captures errors instead of throwing", async () => {
  const c = new ThreadsController(new FakeHost() as never, {
    listFn: async () => {
      throw new Error("down");
    },
  });
  await c.refresh();
  expect(c.error).toBe("down");
  expect(c.loading).toBe(false);
});
```

- [ ] **Step 2: Run to verify FAIL**, then **Step 3: Implement**

```typescript
import type { ReactiveController, ReactiveControllerHost } from "lit";
import {
  deleteThread,
  listThreads,
  renameThread,
  type ThreadMeta,
} from "../agui/api";

type Opts = {
  listFn?: () => Promise<ThreadMeta[]>;
  renameFn?: (id: string, title: string) => Promise<void>;
  deleteFn?: (id: string) => Promise<void>;
};

export class ThreadsController implements ReactiveController {
  threads: ThreadMeta[] = [];
  loading = false;
  error: string | null = null;

  private host: ReactiveControllerHost;
  private listFn: () => Promise<ThreadMeta[]>;
  private renameFn: (id: string, title: string) => Promise<void>;
  private deleteFn: (id: string) => Promise<void>;

  constructor(host: ReactiveControllerHost, opts: Opts = {}) {
    this.host = host;
    this.listFn = opts.listFn ?? (() => listThreads());
    this.renameFn = opts.renameFn ?? ((id, title) => renameThread(id, title));
    this.deleteFn = opts.deleteFn ?? ((id) => deleteThread(id));
    host.addController(this);
  }

  hostConnected(): void {
    void this.refresh();
  }
  hostDisconnected(): void {}

  async refresh(): Promise<void> {
    this.loading = true;
    this.error = null;
    this.host.requestUpdate();
    try {
      this.threads = await this.listFn();
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    } finally {
      this.loading = false;
      this.host.requestUpdate();
    }
  }

  async rename(id: string, title: string): Promise<void> {
    this.threads = this.threads.map((t) => (t.id === id ? { ...t, title } : t));
    this.host.requestUpdate();
    try {
      await this.renameFn(id, title);
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    }
    await this.refresh();
  }

  async remove(id: string): Promise<void> {
    try {
      await this.deleteFn(id);
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    }
    await this.refresh();
  }
}
```

- [ ] **Step 4: Verify PASS; Step 5: lint, typecheck, commit**

```bash
npx vitest run tests/threads-controller.test.ts && npm run lint && npm run typecheck
git add . && git commit -m "feat(concierge): threads controller"
```

---

### Task 7: Message rendering components

**Files:**
- Create: `src/components/chat-message.ts`
- Create: `src/components/tool-call-card.ts`
- Test: `tests/chat-message.test.ts`, `tests/tool-call-card.test.ts`

**Interfaces:**
- Consumes: `ChatMessage`/`AssistantMessage`/`ToolCall` types (Task 3), `renderMarkdown` (Task 4).
- Produces: `<chat-message .message=${ChatMessage}>` — user messages as plain text bubble (right-aligned), assistant messages as sanitized-markdown bubble plus one `<tool-call-card>` per `toolCalls` entry; tool messages render nothing standalone (results display inside the matching card via the `results` property). `<tool-call-card .call=${ToolCall} .result=${string | undefined}>` — collapsed card showing the tool name; expands (`<details>`) to show pretty-printed args and result. `<chat-message>` takes `.results=${Map<string, string>}` (toolCallId → result content) so the parent list can join tool messages onto cards.

- [ ] **Step 1: Write the failing tests**

`tests/chat-message.test.ts`:

```typescript
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
```

`tests/tool-call-card.test.ts`:

```typescript
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
```

- [ ] **Step 2: Run to verify FAIL**, then **Step 3: Implement**

`src/components/tool-call-card.ts`:

```typescript
import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ToolCall } from "../agui/api";

function pretty(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

@customElement("tool-call-card")
export class ToolCallCard extends LitElement {
  @property({ attribute: false }) call!: ToolCall;
  @property({ attribute: false }) result?: string;

  static styles = css`
    details {
      border: 1px solid var(--c-divider);
      border-radius: var(--c-radius, 12px);
      background: var(--c-surface);
      margin: 4px 0;
      font-size: 0.85rem;
    }
    summary {
      cursor: pointer;
      padding: 6px 10px;
      color: var(--c-text-secondary);
    }
    pre {
      margin: 0;
      padding: 8px 10px;
      overflow-x: auto;
      border-top: 1px solid var(--c-divider);
    }
    .pending {
      font-style: italic;
    }
  `;

  render() {
    return html`
      <details>
        <summary>🔧 ${this.call.function.name}</summary>
        <pre>${pretty(this.call.function.arguments)}</pre>
        ${this.result !== undefined
          ? html`<pre>${pretty(this.result)}</pre>`
          : html`<pre class="pending">running…</pre>`}
      </details>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "tool-call-card": ToolCallCard;
  }
}
```

`src/components/chat-message.ts`:

```typescript
import { LitElement, css, html, nothing } from "lit";
import { customElement, property } from "lit/decorators.js";
import { unsafeHTML } from "lit/directives/unsafe-html.js";
import type { ChatMessage } from "../agui/api";
import { renderMarkdown } from "../markdown";
import "./tool-call-card";

@customElement("chat-message")
export class ChatMessageEl extends LitElement {
  @property({ attribute: false }) message!: ChatMessage;
  @property({ attribute: false }) results: Map<string, string> = new Map();

  static styles = css`
    .bubble {
      max-width: 46rem;
      padding: 8px 14px;
      border-radius: var(--c-radius, 12px);
      margin: 4px 0;
      overflow-wrap: anywhere;
    }
    .user {
      background: var(--c-primary);
      color: var(--c-on-primary);
      margin-left: auto;
      width: fit-content;
      white-space: pre-wrap;
    }
    .assistant {
      background: var(--c-surface);
      border: 1px solid var(--c-divider);
    }
    .assistant :first-child {
      margin-top: 0;
    }
    .assistant :last-child {
      margin-bottom: 0;
    }
  `;

  render() {
    const m = this.message;
    if (m.role === "user") {
      return html`<div class="bubble user">${m.content}</div>`;
    }
    if (m.role === "assistant") {
      return html`
        ${(m.toolCalls ?? []).map(
          (call) => html`<tool-call-card
            .call=${call}
            .result=${this.results.get(call.id)}
          ></tool-call-card>`,
        )}
        ${m.content
          ? html`<div class="bubble assistant">
              ${unsafeHTML(renderMarkdown(m.content))}
            </div>`
          : nothing}
      `;
    }
    return nothing; // tool messages render inside their card via `results`
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "chat-message": ChatMessageEl;
  }
}
```

- [ ] **Step 4: Verify PASS; Step 5: lint, typecheck, commit**

```bash
npx vitest run tests/chat-message.test.ts tests/tool-call-card.test.ts && npm run lint && npm run typecheck
git add . && git commit -m "feat(concierge): message and tool-call rendering components"
```

---

### Task 8: HITL approval card

**Files:**
- Create: `src/components/approval-card.ts`
- Test: `tests/approval-card.test.ts`

**Interfaces:**
- Consumes: `Interrupt` (Task 2).
- Produces: `<approval-card .interrupt=${Interrupt} .toolName=${string | undefined} .toolArgs=${string | undefined}>` — a highlighted card ("Concierge wants to run <tool>") showing pretty args; **Approve** and **Deny** `<button>`s dispatching a composed `resolve-interrupt` CustomEvent with `detail: {interruptId, approved: boolean}`. Buttons disable after click.

- [ ] **Step 1: Write the failing test**

`tests/approval-card.test.ts`:

```typescript
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
```

- [ ] **Step 2: Run to verify FAIL**, then **Step 3: Implement `src/components/approval-card.ts`**

```typescript
import { LitElement, css, html, nothing } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { Interrupt } from "../agui/events";

function pretty(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

@customElement("approval-card")
export class ApprovalCard extends LitElement {
  @property({ attribute: false }) interrupt!: Interrupt;
  @property() toolName?: string;
  @property() toolArgs?: string;
  @state() private resolved = false;

  static styles = css`
    .card {
      border: 1px solid var(--c-warning);
      border-radius: var(--c-radius, 12px);
      background: var(--c-surface);
      padding: 12px 14px;
      margin: 8px 0;
    }
    pre {
      overflow-x: auto;
      font-size: 0.85rem;
    }
    .actions {
      display: flex;
      gap: 8px;
    }
    button {
      border: none;
      border-radius: 8px;
      padding: 8px 16px;
      cursor: pointer;
      font: inherit;
    }
    button:disabled {
      opacity: 0.5;
      cursor: default;
    }
    .approve {
      background: var(--c-primary);
      color: var(--c-on-primary);
    }
    .deny {
      background: transparent;
      border: 1px solid var(--c-divider);
      color: var(--c-text);
    }
  `;

  private resolve(approved: boolean): void {
    this.resolved = true;
    this.dispatchEvent(
      new CustomEvent("resolve-interrupt", {
        detail: { interruptId: this.interrupt.id, approved },
        bubbles: true,
        composed: true,
      }),
    );
  }

  render() {
    return html`
      <div class="card" role="group" aria-label="Tool approval required">
        <p>
          Concierge wants to run
          <strong>${this.toolName ?? this.interrupt.toolCallId ?? "a tool"}</strong>
        </p>
        ${this.toolArgs ? html`<pre>${pretty(this.toolArgs)}</pre>` : nothing}
        <div class="actions">
          <button
            class="approve"
            ?disabled=${this.resolved}
            @click=${() => this.resolve(true)}
          >
            Approve
          </button>
          <button
            class="deny"
            ?disabled=${this.resolved}
            @click=${() => this.resolve(false)}
          >
            Deny
          </button>
        </div>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "approval-card": ApprovalCard;
  }
}
```

- [ ] **Step 4: Verify PASS; Step 5: lint, typecheck, commit**

```bash
npx vitest run tests/approval-card.test.ts && npm run lint && npm run typecheck
git add . && git commit -m "feat(concierge): HITL approval card"
```

---

### Task 9: App shell — chat panel, thread sidebar, composer, wiring

**Files:**
- Create: `src/components/chat-panel.ts`
- Create: `src/components/thread-sidebar.ts`
- Modify: `src/components/concierge-app.ts` (replace the Task-1 placeholder)
- Test: `tests/app-shell.test.ts`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `<thread-sidebar .threads=${ThreadMeta[]} .activeId=${string | null}>` — `<nav aria-label="Conversations">`; "New chat" button dispatching `new-thread`; one button per thread (title or "Untitled") dispatching `select-thread` `{detail: {id}}`; a per-thread delete button dispatching `delete-thread` `{detail: {id}}`.
  - `<chat-panel>` owns a `ChatController`; renders `<main>` with: messages list in a scrolling `div[aria-live="polite"]` mapping `messages` → `<chat-message>` (building `results` from tool messages: `Map(toolMessages.map(m => [m.toolCallId, m.content]))`); one `<approval-card>` per `pendingInterrupts` (deriving toolName/toolArgs from the assistant message's matching `toolCalls` entry via `interrupt.toolCallId`); an error banner when `error`; a composer `<form>` (textarea + submit) that calls `controller.send()`, disabled while `streaming`; re-emits the controller's `turn-finished`. Exposes `openThread(id)` for the app shell.
  - `<concierge-app>` composes both, owns a `ThreadsController`, handles: `new-thread` → `chatPanel.openThread(null)`; `select-thread` → `openThread(id)`; `delete-thread` → `threads.remove(id)` (+ reset chat if active); `turn-finished` → `threads.refresh()` (picks up server-generated titles); a theme toggle button calling `applyTheme`.

- [ ] **Step 1: Write the failing test**

`tests/app-shell.test.ts`:

```typescript
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
```

- [ ] **Step 2: Run to verify FAIL**, then **Step 3: Implement**

`src/components/thread-sidebar.ts`:

```typescript
import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ThreadMeta } from "../agui/api";

@customElement("thread-sidebar")
export class ThreadSidebar extends LitElement {
  @property({ attribute: false }) threads: ThreadMeta[] = [];
  @property() activeId: string | null = null;

  static styles = css`
    nav {
      width: 230px;
      height: 100%;
      overflow-y: auto;
      background: var(--c-surface);
      border-right: 1px solid var(--c-divider);
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
      padding: 8px;
      gap: 2px;
    }
    button {
      font: inherit;
      text-align: left;
      border: none;
      background: transparent;
      color: var(--c-text);
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      gap: 6px;
    }
    button:hover,
    button.active {
      background: color-mix(in srgb, var(--c-primary) 12%, transparent);
    }
    .new-thread {
      font-weight: 600;
      color: var(--c-primary);
    }
    .delete {
      padding: 0 4px;
      color: var(--c-text-secondary);
    }
    .row {
      display: flex;
      align-items: center;
    }
    .row > .thread {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  `;

  private emit(name: string, id?: string): void {
    this.dispatchEvent(
      new CustomEvent(name, {
        detail: id ? { id } : undefined,
        bubbles: true,
        composed: true,
      }),
    );
  }

  render() {
    return html`
      <nav aria-label="Conversations">
        <button class="new-thread" @click=${() => this.emit("new-thread")}>
          ＋ New chat
        </button>
        ${this.threads.map(
          (t) => html`
            <div class="row">
              <button
                class="thread ${t.id === this.activeId ? "active" : ""}"
                @click=${() => this.emit("select-thread", t.id)}
              >
                ${t.title ?? "Untitled"}
              </button>
              <button
                class="delete"
                aria-label="Delete conversation"
                @click=${() => this.emit("delete-thread", t.id)}
              >
                ✕
              </button>
            </div>
          `,
        )}
      </nav>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "thread-sidebar": ThreadSidebar;
  }
}
```

`src/components/chat-panel.ts`:

```typescript
import { LitElement, css, html, nothing } from "lit";
import { customElement } from "lit/decorators.js";
import type { AssistantMessage, ToolMessage } from "../agui/api";
import { ChatController } from "../state/chat-controller";
import "./approval-card";
import "./chat-message";

@customElement("chat-panel")
export class ChatPanel extends LitElement {
  readonly controller = new ChatController(this);

  static styles = css`
    main {
      display: flex;
      flex-direction: column;
      height: 100%;
      min-width: 0;
    }
    .messages {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
    }
    form {
      display: flex;
      gap: 8px;
      padding: 12px 16px;
      border-top: 1px solid var(--c-divider);
    }
    textarea {
      flex: 1;
      font: inherit;
      resize: none;
      border: 1px solid var(--c-divider);
      border-radius: var(--c-radius, 12px);
      background: var(--c-surface);
      color: var(--c-text);
      padding: 10px 12px;
      min-height: 2.6rem;
    }
    button[type="submit"] {
      font: inherit;
      border: none;
      border-radius: var(--c-radius, 12px);
      background: var(--c-primary);
      color: var(--c-on-primary);
      padding: 0 20px;
      cursor: pointer;
    }
    button:disabled {
      opacity: 0.5;
      cursor: default;
    }
    .error {
      color: var(--c-error);
      padding: 8px 16px;
    }
  `;

  async openThread(id: string | null): Promise<void> {
    await this.controller.openThread(id);
  }

  private toolResults(): Map<string, string> {
    return new Map(
      this.controller.messages
        .filter((m): m is ToolMessage => m.role === "tool")
        .map((m) => [m.toolCallId, m.content]),
    );
  }

  private interruptToolInfo(toolCallId?: string): {
    name?: string;
    args?: string;
  } {
    if (!toolCallId) return {};
    const call = this.controller.messages
      .filter((m): m is AssistantMessage => m.role === "assistant")
      .flatMap((m) => m.toolCalls ?? [])
      .find((c) => c.id === toolCallId);
    return call ? { name: call.function.name, args: call.function.arguments } : {};
  }

  private onSubmit(e: Event): void {
    e.preventDefault();
    const area = this.shadowRoot!.querySelector("textarea")!;
    const text = area.value.trim();
    if (!text) return;
    area.value = "";
    void this.controller.send(text);
  }

  private onResolve(e: Event): void {
    const { interruptId, approved } = (e as CustomEvent).detail;
    void this.controller.resolveInterrupt(interruptId, approved);
  }

  render() {
    const c = this.controller;
    const results = this.toolResults();
    return html`
      <main @resolve-interrupt=${this.onResolve}>
        <div class="messages" aria-live="polite">
          ${c.messages.map(
            (m) => html`<chat-message .message=${m} .results=${results}></chat-message>`,
          )}
          ${c.pendingInterrupts.map((i) => {
            const info = this.interruptToolInfo(i.toolCallId);
            return html`<approval-card
              .interrupt=${i}
              .toolName=${info.name}
              .toolArgs=${info.args}
            ></approval-card>`;
          })}
        </div>
        ${c.error ? html`<p class="error" role="alert">${c.error}</p>` : nothing}
        <form @submit=${this.onSubmit}>
          <textarea
            aria-label="Message Concierge"
            placeholder="Ask about your home…"
            ?disabled=${c.streaming}
          ></textarea>
          <button type="submit" ?disabled=${c.streaming}>Send</button>
        </form>
      </main>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "chat-panel": ChatPanel;
  }
}
```

(`ChatController.setRunFnForTests` already exists from Task 5.)

`src/components/concierge-app.ts` (replace placeholder):

```typescript
import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";
import { applyTheme, currentTheme } from "../theme";
import { ThreadsController } from "../state/threads-controller";
import "./chat-panel";
import "./thread-sidebar";
import type { ChatPanel } from "./chat-panel";

@customElement("concierge-app")
export class ConciergeApp extends LitElement {
  private threads = new ThreadsController(this);
  @state() private activeId: string | null = null;

  static styles = css`
    :host {
      display: flex;
      height: 100vh;
    }
    .content {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 16px;
      border-bottom: 1px solid var(--c-divider);
      background: var(--c-surface);
    }
    header h1 {
      font-size: 1rem;
      margin: 0;
    }
    .theme-toggle {
      font: inherit;
      border: none;
      background: transparent;
      cursor: pointer;
      color: var(--c-text);
    }
    chat-panel {
      flex: 1;
      min-height: 0;
    }
  `;

  private get panel(): ChatPanel {
    return this.shadowRoot!.querySelector("chat-panel")!;
  }

  private async onSelect(e: Event): Promise<void> {
    const id = (e as CustomEvent).detail.id as string;
    this.activeId = id;
    await this.panel.openThread(id);
  }

  private async onNew(): Promise<void> {
    this.activeId = null;
    await this.panel.openThread(null);
  }

  private async onDelete(e: Event): Promise<void> {
    const id = (e as CustomEvent).detail.id as string;
    await this.threads.remove(id);
    if (this.activeId === id) await this.onNew();
  }

  private toggleTheme(): void {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
    this.requestUpdate();
  }

  firstUpdated(): void {
    void this.onNew();
  }

  render() {
    return html`
      <thread-sidebar
        .threads=${this.threads.threads}
        .activeId=${this.activeId}
        @select-thread=${this.onSelect}
        @new-thread=${this.onNew}
        @delete-thread=${this.onDelete}
      ></thread-sidebar>
      <div class="content">
        <header>
          <h1>Concierge</h1>
          <button
            class="theme-toggle"
            aria-label="Toggle theme"
            @click=${this.toggleTheme}
          >
            ${currentTheme() === "dark" ? "☀️" : "🌙"}
          </button>
        </header>
        <chat-panel @turn-finished=${() => void this.threads.refresh()}></chat-panel>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "concierge-app": ConciergeApp;
  }
}
```

Note: `ChatController` dispatches `turn-finished` on its host — the `<chat-panel>` element itself — and `<concierge-app>`'s `@turn-finished` listener sits directly on that element, so no `bubbles`/`composed` flags are needed on the CustomEvent.

- [ ] **Step 4: Update the Task-1 shell test** — `tests/concierge-app.test.ts`'s landmark assertion should now find `thread-sidebar` + `chat-panel` (adjust to `expect(root.querySelector("thread-sidebar")).not.toBeNull()`; the `<main>` landmark moved into `<chat-panel>`). Run the FULL FE suite: `npx vitest run` — all PASS.

- [ ] **Step 5: Lint, typecheck, build, commit**

```bash
npm run lint && npm run typecheck && npm run build
git add . && git commit -m "feat(concierge): app shell with sidebar, chat panel, and HITL wiring"
```

---

### Task 10: Backend static/SPA serving + built-frontend smoke

**Files:**
- Modify: `homeassistant-addon-concierge-dev/backend/concierge/config.py` (add `static_dir: Path | None = None`)
- Modify: `homeassistant-addon-concierge-dev/backend/concierge/web.py` (add static/SPA routes when `settings.static_dir` is a directory)
- Test: `homeassistant-addon-concierge-dev/backend/tests/test_static.py`

**Interfaces:**
- Consumes: existing `create_app` (all current routes unchanged).
- Produces: when `settings.static_dir` points at an existing directory, `create_app` registers — LAST, so it never shadows `/agui`/`/threads` — `GET /{full_path:path}` serving real files under `static_dir` (path-traversal safe: resolved candidate must be inside the resolved `static_dir`) and falling back to `index.html` for anything else (SPA routes). When `static_dir` is `None`/missing, behavior is exactly as today.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_static.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from concierge.config import Settings
from concierge.sessions import SessionStore
from concierge.web import create_app


def make_app(tmp_path: Path, static_dir: Path | None):
    settings = Settings(data_dir=tmp_path, static_dir=static_dir)

    class _NoAgent:  # static routes never touch the agent
        async def __aenter__(self) -> "_NoAgent":
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    store = SessionStore(tmp_path / "db.sqlite")
    return create_app(settings, agent=_NoAgent(), store=store)  # type: ignore[arg-type]


def write_site(tmp_path: Path) -> Path:
    site = tmp_path / "dist"
    site.mkdir()
    (site / "index.html").write_text("<html>app</html>")
    (site / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("nope")
    return site


def test_serves_real_files_and_spa_fallback(tmp_path: Path) -> None:
    site = write_site(tmp_path)
    with TestClient(make_app(tmp_path, site)) as c:
        assert c.get("/app.js").text == "console.log(1)"
        assert "app" in c.get("/").text
        assert "app" in c.get("/some/spa/route").text  # fallback


def test_path_traversal_is_blocked(tmp_path: Path) -> None:
    site = write_site(tmp_path)
    with TestClient(make_app(tmp_path, site)) as c:
        resp = c.get("/%2e%2e/secret.txt")
        assert "nope" not in resp.text


def test_api_routes_not_shadowed(tmp_path: Path) -> None:
    site = write_site(tmp_path)
    with TestClient(make_app(tmp_path, site)) as c:
        assert c.get("/threads").json() == []


def test_no_static_dir_means_no_route(tmp_path: Path) -> None:
    with TestClient(make_app(tmp_path, None)) as c:
        assert c.get("/anything").status_code == 404
```

Note: the `_NoAgent` stand-in must survive `create_app`'s lifespan (`async with agent:`) — hence the async-context methods. If `create_app` uses other agent attributes at construction, extend the stub minimally (do not touch the lifespan design).

- [ ] **Step 2: Run to verify FAIL**

Run: `cd homeassistant-addon-concierge-dev/backend && uv run pytest tests/test_static.py -v`
Expected: FAIL (`Settings` has no field `static_dir`).

- [ ] **Step 3: Implement**

`concierge/config.py` — add below `data_dir`:

```python
    # Built frontend directory; when set (and existing) the app serves it
    # with an SPA fallback. None in tests/dev keeps the API pure.
    static_dir: Path | None = None
```

`concierge/web.py` — at the END of `create_app` (after all API routes), add:

```python
    static_dir = settings.static_dir
    if static_dir is not None and static_dir.is_dir():
        root = static_dir.resolve()
        index_file = root / "index.html"

        @app.get("/{full_path:path}")
        async def spa(full_path: str) -> Response:
            """Serve real static files; fall back to index.html (SPA).

            Registered LAST so the explicit /agui and /threads routes always
            win. Path-traversal safe: the resolved candidate must stay under
            the static root.
            """
            candidate = (root / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(root):
                return FileResponse(candidate)
            return FileResponse(index_file)
```

(Import `FileResponse` from `fastapi.responses` alongside the existing imports.)

- [ ] **Step 4: Verify PASS + full backend suite**

Run: `uv run pytest tests/test_static.py -v` → 4 PASS. Then full: `uv run pytest -q` (all pass), `uv run ruff check .`, `uv run mypy concierge/`.

- [ ] **Step 5: End-to-end smoke with the real built frontend**

```bash
cd ../frontend && npm run build && cd ../backend
CONCIERGE_DATA_DIR=/tmp/concierge-fe-smoke CONCIERGE_HA_URL=http://127.0.0.1:1 \
CONCIERGE_HA_TOKEN=fake CONCIERGE_API_KEY=dummy \
CONCIERGE_STATIC_DIR="$(cd ../frontend/dist && pwd)" \
uv run python -m concierge &
sleep 3
curl -s localhost:8098/ | head -3          # expect the built index.html
curl -s localhost:8098/threads             # expect [] (API not shadowed)
curl -sI localhost:8098/assets/ | head -1  # any asset route resolves (200 or index fallback)
kill %1 2>/dev/null; pkill -f "python -m concierge" 2>/dev/null || true
```

Expected: index.html served at `/`, `/threads` still returns JSON.

- [ ] **Step 6: Commit**

```bash
cd ../../..   # worktree root
git add homeassistant-addon-concierge-dev/backend
git commit -m "feat(concierge): serve the built frontend with SPA fallback"
```

---

### Task 11: Repo lint wiring + dev docs

**Files:**
- Modify: `lefthook.yml` (worktree root) — add a frontend job next to `mypy-concierge`
- Create: `homeassistant-addon-concierge-dev/frontend/README.md` (dev workflow: `uv run python -m concierge` + `npm run dev` proxy; build; test)

**Interfaces:**
- Produces: pre-commit coverage for the FE (`lint` + `typecheck` on staged frontend files) and a 20-line contributor README.

- [ ] **Step 1: Add the lefthook job** (same `jobs:` list as `mypy-concierge`, matching indentation):

```yaml
          - name: frontend-concierge
            glob: "homeassistant-addon-concierge-dev/frontend/**/*.{ts,js,html,css,json}"
            run: cd homeassistant-addon-concierge-dev/frontend && npm run lint && npm run typecheck
```

- [ ] **Step 2: Write `frontend/README.md`**

```markdown
# Concierge frontend

Lit + TypeScript SPA, built with Vite, served by the backend (FastAPI) as
static files. Speaks the AG-UI protocol over SSE — see
`docs/superpowers/notes/2026-07-10-backend-handoff.md` for the wire contract.

## Dev workflow

    # terminal 1 — backend on :8098
    cd ../backend
    CONCIERGE_DATA_DIR=/tmp/concierge-dev CONCIERGE_HA_URL=... \
    CONCIERGE_HA_TOKEN=... CONCIERGE_API_KEY=... uv run python -m concierge

    # terminal 2 — Vite dev server with /agui + /threads proxied
    npm install
    npm run dev

## Checks

    npm run test        # vitest (happy-dom)
    npm run lint        # eslint
    npm run typecheck   # tsc --noEmit
    npm run build       # tsc + vite build -> dist/

All API paths are RELATIVE (`./agui`) — Supervisor ingress serves the app
under a dynamic path prefix, so absolute paths would break. Keep it that way.
```

- [ ] **Step 3: Validate + full check + commit**

```bash
cd homeassistant-addon-concierge-dev/frontend && npm run lint && npm run typecheck && npx vitest run && npm run build
cd ../../ && git add lefthook.yml homeassistant-addon-concierge-dev/frontend/README.md
git commit -m "chore(concierge): frontend lint wiring and dev docs"
```

---

## Definition of done (Plan 2)

- `npx vitest run` green in `frontend/` (~25 tests across 10 files); `npm run lint`, `npm run typecheck`, `npm run build` clean.
- Backend suite still green (`uv run pytest -q`), ruff + mypy clean, including the 4 new static-serving tests.
- End-to-end smoke: the **built** frontend served by `python -m concierge` at `/`, API routes unshadowed.
- Every API path in `src/` is relative (`grep -rn '"/agui\|"/threads' frontend/src` → no matches).
- All commits on `feat/concierge-addon`; findings affecting Plan 3 appended to `docs/superpowers/notes/2026-07-10-backend-handoff.md` or a sibling note.
