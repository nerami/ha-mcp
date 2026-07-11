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
