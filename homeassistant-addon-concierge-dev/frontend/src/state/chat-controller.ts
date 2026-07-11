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
