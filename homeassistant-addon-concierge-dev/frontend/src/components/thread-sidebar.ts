import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import type { ThreadMeta } from "../agui/api";

@customElement("thread-sidebar")
export class ThreadSidebar extends LitElement {
  @property({ attribute: false }) threads: ThreadMeta[] = [];
  @property() activeId: string | null = null;

  // Id of the thread whose title is being edited inline, or null when no row
  // is in edit mode. `draftTitle` is the in-progress input value.
  @state() private editingId: string | null = null;
  @state() private draftTitle = "";

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
    .delete,
    .rename {
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
    .rename-input {
      flex: 1;
      min-width: 0;
      font: inherit;
      color: var(--c-text);
      background: var(--c-bg);
      border: 1px solid var(--c-primary);
      border-radius: 8px;
      padding: 7px 9px;
    }
    .save-rename {
      padding: 0 4px;
      color: var(--c-primary);
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

  private startRename(t: ThreadMeta): void {
    this.editingId = t.id;
    this.draftTitle = t.title ?? "";
  }

  private cancelRename(): void {
    this.editingId = null;
    this.draftTitle = "";
  }

  // Confirm the edit. A blank/whitespace-only title is discarded (no event),
  // matching the "empty titles are not submitted" rule.
  private commitRename(id: string): void {
    if (this.editingId !== id) return;
    const title = this.draftTitle.trim();
    this.editingId = null;
    this.draftTitle = "";
    if (title) {
      this.dispatchEvent(
        new CustomEvent("rename-thread", {
          detail: { id, title },
          bubbles: true,
          composed: true,
        }),
      );
    }
  }

  private onEditKeydown(e: KeyboardEvent, id: string): void {
    if (e.key === "Enter") {
      e.preventDefault();
      this.commitRename(id);
    } else if (e.key === "Escape") {
      e.preventDefault();
      this.cancelRename();
    }
  }

  // Focus (and select) the input when a row enters edit mode. Guarded so it
  // does not re-select on every keystroke re-render.
  updated(): void {
    if (this.editingId === null) return;
    const input =
      this.shadowRoot?.querySelector<HTMLInputElement>(".rename-input");
    if (input && this.shadowRoot?.activeElement !== input) {
      input.focus();
      input.select();
    }
  }

  private renderRow(t: ThreadMeta) {
    if (t.id === this.editingId) {
      return html`
        <div class="row">
          <input
            class="rename-input"
            aria-label="Conversation title"
            .value=${this.draftTitle}
            @input=${(e: Event) =>
              (this.draftTitle = (e.target as HTMLInputElement).value)}
            @keydown=${(e: KeyboardEvent) => this.onEditKeydown(e, t.id)}
            @blur=${() => this.commitRename(t.id)}
          />
          <button
            class="save-rename"
            aria-label="Save conversation name"
            @click=${() => this.commitRename(t.id)}
          >
            ✓
          </button>
        </div>
      `;
    }
    return html`
      <div class="row">
        <button
          class="thread ${t.id === this.activeId ? "active" : ""}"
          @click=${() => this.emit("select-thread", t.id)}
        >
          ${t.title ?? "Untitled"}
        </button>
        <button
          class="rename"
          aria-label="Rename conversation"
          @click=${() => this.startRename(t)}
        >
          ✎
        </button>
        <button
          class="delete"
          aria-label="Delete conversation"
          @click=${() => this.emit("delete-thread", t.id)}
        >
          ✕
        </button>
      </div>
    `;
  }

  render() {
    return html`
      <nav aria-label="Conversations">
        <button class="new-thread" @click=${() => this.emit("new-thread")}>
          ＋ New chat
        </button>
        ${this.threads.map((t) => this.renderRow(t))}
      </nav>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "thread-sidebar": ThreadSidebar;
  }
}
