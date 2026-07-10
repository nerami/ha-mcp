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
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
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
