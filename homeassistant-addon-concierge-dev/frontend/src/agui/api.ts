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
  payload: { approved: boolean; editedArgs?: object; reason?: string };
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
  fetchFn: FetchFn = fetch,
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

export async function listThreads(fetchFn: FetchFn = fetch): Promise<ThreadMeta[]> {
  return json(await fetchFn("./threads"), "list threads");
}

export async function getThreadMessages(
  id: string,
  fetchFn: FetchFn = fetch,
): Promise<ChatMessage[]> {
  return json(await fetchFn(`./threads/${encodeURIComponent(id)}`), "get thread");
}

export async function renameThread(
  id: string,
  title: string,
  fetchFn: FetchFn = fetch,
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
  fetchFn: FetchFn = fetch,
): Promise<void> {
  const resp = await fetchFn(`./threads/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!resp.ok) throw new Error(`delete failed: HTTP ${resp.status}`);
}
