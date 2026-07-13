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
    .thinking {
      display: inline-flex;
      gap: 5px;
      align-items: center;
      width: fit-content;
      background: var(--c-surface);
      border: 1px solid var(--c-divider);
      border-radius: var(--c-radius, 12px);
      padding: 12px 14px;
      margin: 4px 0;
    }
    .thinking .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--c-text);
      opacity: 0.3;
      animation: thinking-pulse 1.2s infinite ease-in-out;
    }
    .thinking .dot:nth-child(2) {
      animation-delay: 0.2s;
    }
    .thinking .dot:nth-child(3) {
      animation-delay: 0.4s;
    }
    @keyframes thinking-pulse {
      0%,
      60%,
      100% {
        opacity: 0.25;
        transform: translateY(0);
      }
      30% {
        opacity: 0.85;
        transform: translateY(-3px);
      }
    }
    @media (prefers-reduced-motion: reduce) {
      .thinking .dot {
        animation: none;
        opacity: 0.5;
      }
    }
  `;

  /**
   * Show a "thinking" affordance during the turn's dead air: after the user
   * sends (or a tool returns) and before the assistant is visibly producing
   * text or a tool call. Hides the moment real assistant output appears (which
   * carries its own progress) and while an approval is pending (streaming is
   * already false there — the approval-card is the affordance).
   */
  private isThinking(): boolean {
    const c = this.controller;
    if (!c.streaming) return false;
    const last = c.messages[c.messages.length - 1];
    const producing =
      last?.role === "assistant" &&
      ((last.content?.length ?? 0) > 0 || (last.toolCalls?.length ?? 0) > 0);
    return !producing;
  }

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
    const c = this.controller;
    // Keep the draft: send() silently no-ops in these states, so clearing
    // the textarea here would lose the user's message.
    if (c.streaming || c.loading || c.threadId === null) return;
    const area = this.shadowRoot!.querySelector("textarea")!;
    const text = area.value.trim();
    if (!text) return;
    area.value = "";
    void c.send(text);
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
          ${this.isThinking()
            ? html`<div class="thinking" role="status" aria-label="Concierge is thinking">
                <span class="dot"></span><span class="dot"></span><span class="dot"></span>
              </div>`
            : nothing}
        </div>
        ${c.error ? html`<p class="error" role="alert">${c.error}</p>` : nothing}
        <form @submit=${this.onSubmit}>
          <textarea
            aria-label="Message Concierge"
            placeholder="Ask about your home…"
            ?disabled=${c.streaming || c.loading}
          ></textarea>
          <button type="submit" ?disabled=${c.streaming || c.loading}>
            Send
          </button>
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
