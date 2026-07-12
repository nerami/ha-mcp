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
  /** True while an existing thread's messages are being rehydrated. */
  loading = false;
  pendingInterrupts: Interrupt[] = [];
  error: string | null = null;

  private runFn: RunFn;
  private loadFn: LoadFn;
  private host: Host;
  /** Bumped by openThread(); a turn started under an older epoch is stale. */
  private turnEpoch = 0;
  /**
   * Bumped by runTurn(); distinguishes turns within the SAME epoch (e.g. a
   * resume started while the prior turn's stream is still draining past
   * RUN_FINISHED). The epoch alone can't tell send()'s turn apart from the
   * resolveInterrupt() turn that follows it without a new openThread() call.
   */
  private turnSeq = 0;

  constructor(host: Host, opts: { runFn?: RunFn; loadFn?: LoadFn } = {}) {
    this.host = host;
    this.runFn = opts.runFn ?? postRun;
    this.loadFn = opts.loadFn ?? getThreadMessages;
    host.addController(this);
  }

  hostConnected(): void {}
  hostDisconnected(): void {}

  async openThread(id: string | null): Promise<void> {
    // Bump the epoch to invalidate any in-flight turn AND any still-pending
    // rehydration from an earlier openThread() call.
    const epoch = ++this.turnEpoch;
    this.streaming = false;
    this.loading = false;
    this.error = null;
    this.pendingInterrupts = [];
    if (id === null) {
      this.threadId = crypto.randomUUID();
      this.messages = [];
    } else {
      // Block send() while rehydrating: its threadId guard sees null.
      this.threadId = null;
      this.messages = [];
      this.loading = true;
      this.host.requestUpdate();
      try {
        const loaded = await this.loadFn(id);
        if (this.turnEpoch !== epoch) return; // superseded by a newer open
        this.threadId = id;
        this.messages = loaded;
      } finally {
        // Epoch-guarded: a superseded open's settle (resolve OR reject) must
        // not clear the winning open's loading flag. requestUpdate here so a
        // rejected load (which skips the tail below) still re-enables the UI.
        if (this.turnEpoch === epoch) {
          this.loading = false;
          this.host.requestUpdate();
        }
      }
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
    // Never send a resume for an interrupt id we don't hold.
    if (!this.pendingInterrupts.some((i) => i.id === interruptId)) return;
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
    const epoch = this.turnEpoch;
    const turn = ++this.turnSeq;
    this.streaming = true;
    this.error = null;
    this.host.requestUpdate();
    let finishedCleanly = false;
    try {
      for await (const ev of this.runFn(input)) {
        // thread switched (epoch) OR a newer turn started on the same
        // thread while this one drains past RUN_FINISHED (seq): stale,
        // discard rather than fold into shared state.
        if (this.turnEpoch !== epoch || this.turnSeq !== turn) break;
        this.fold(ev);
        this.host.requestUpdate();
        if (ev.type === "RUN_ERROR") break; // turn-terminal per contract
        if (ev.type === "RUN_FINISHED") {
          finishedCleanly = true;
          // Act on RUN_FINISHED, never on stream close: the backend holds
          // the SSE response open ~1 title-model round-trip past this event
          // for server-side titling. Unblock the UI right here so approvals
          // aren't dropped and approval-cards don't go permanently dead
          // during that window. Deliberately keep draining below (no
          // break/cancel): disconnecting here could kill the in-flight
          // titling call server-side.
          this.streaming = false;
          this.host.requestUpdate();
        }
      }
    } catch (e) {
      if (this.turnEpoch === epoch && this.turnSeq === turn) {
        this.error = e instanceof Error ? e.message : String(e);
      }
    } finally {
      // A stale/superseded turn must not touch a newer turn's state or emit
      // its events; openThread() already reset streaming for a new epoch,
      // and a newer same-epoch turn (resume-while-draining) owns `streaming`
      // once it starts.
      if (this.turnEpoch === epoch && this.turnSeq === turn) {
        this.streaming = false;
        this.host.requestUpdate();
        // turn-finished fires after ANY RUN_FINISHED — including
        // outcome.type === "interrupt" (the backend generates thread titles
        // even for gated first turns, and consumers refresh titles on this
        // event) — but never after RUN_ERROR. Kept here (stream close, not
        // RUN_FINISHED) deliberately: this is when the title actually
        // exists server-side, so the refresh timing this event drives is
        // still correct even though `streaming` itself now unblocks earlier.
        if (finishedCleanly && this.host.dispatchEvent) {
          this.host.dispatchEvent(new CustomEvent("turn-finished"));
        }
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
        this.messages = [...this.messages];
        break;
      }
      case "TOOL_CALL_ARGS": {
        const call = this.messages
          .filter((m): m is AssistantMessage => m.role === "assistant")
          .flatMap((m) => m.toolCalls ?? [])
          .find((c) => c.id === ev.toolCallId);
        if (call) call.function.arguments += ev.delta;
        this.messages = [...this.messages];
        break;
      }
      case "TOOL_CALL_RESULT": {
        this.messages = [
          ...this.messages,
          { id: ev.messageId, role: "tool", toolCallId: ev.toolCallId, content: ev.content },
        ];
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
