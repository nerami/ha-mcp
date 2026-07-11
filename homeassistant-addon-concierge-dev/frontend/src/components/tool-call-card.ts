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
