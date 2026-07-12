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
    // Abandoned streams (consumer breaks out early, e.g. RUN_ERROR or a
    // thread switch mid-turn) must stop downloading rather than keep
    // draining in the background. A no-op if the stream already ended
    // naturally.
    void reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
