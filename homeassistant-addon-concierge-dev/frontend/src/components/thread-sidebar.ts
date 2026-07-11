import { LitElement, css, html } from "lit";
import { customElement, property } from "lit/decorators.js";
import type { ThreadMeta } from "../agui/api";

@customElement("thread-sidebar")
export class ThreadSidebar extends LitElement {
  @property({ attribute: false }) threads: ThreadMeta[] = [];
  @property() activeId: string | null = null;

  static styles = css`
    nav {
      width: 230px;
      height: 100%;
      overflow-y: auto;
      background: var(--c-surface);
      border-right: 1px solid var(--c-divider);
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
      padding: 8px;
      gap: 2px;
    }
    button {
      font: inherit;
      text-align: left;
      border: none;
      background: transparent;
      color: var(--c-text);
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      gap: 6px;
    }
    button:hover,
    button.active {
      background: color-mix(in srgb, var(--c-primary) 12%, transparent);
    }
    .new-thread {
      font-weight: 600;
      color: var(--c-primary);
    }
    .delete {
      padding: 0 4px;
      color: var(--c-text-secondary);
    }
    .row {
      display: flex;
      align-items: center;
    }
    .row > .thread {
      flex: 1;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  `;

  private emit(name: string, id?: string): void {
    this.dispatchEvent(
      new CustomEvent(name, {
        detail: id ? { id } : undefined,
        bubbles: true,
        composed: true,
      }),
    );
  }

  render() {
    return html`
      <nav aria-label="Conversations">
        <button class="new-thread" @click=${() => this.emit("new-thread")}>
          ＋ New chat
        </button>
        ${this.threads.map(
          (t) => html`
            <div class="row">
              <button
                class="thread ${t.id === this.activeId ? "active" : ""}"
                @click=${() => this.emit("select-thread", t.id)}
              >
                ${t.title ?? "Untitled"}
              </button>
              <button
                class="delete"
                aria-label="Delete conversation"
                @click=${() => this.emit("delete-thread", t.id)}
              >
                ✕
              </button>
            </div>
          `,
        )}
      </nav>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "thread-sidebar": ThreadSidebar;
  }
}
