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
