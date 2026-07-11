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
