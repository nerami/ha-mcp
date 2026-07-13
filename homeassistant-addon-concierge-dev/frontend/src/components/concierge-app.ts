import { LitElement, css, html } from "lit";
import { customElement, state } from "lit/decorators.js";
import { applyTheme, currentTheme } from "../theme";
import { ThreadsController } from "../state/threads-controller";
import "./chat-panel";
import "./thread-sidebar";
import type { ChatPanel } from "./chat-panel";

@customElement("concierge-app")
export class ConciergeApp extends LitElement {
  // Public for tests (mirrors chat-panel's public `controller` precedent).
  readonly threads = new ThreadsController(this);
  @state() private activeId: string | null = null;

  static styles = css`
    :host {
      display: flex;
      height: 100vh;
    }
    .content {
      flex: 1;
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 16px;
      border-bottom: 1px solid var(--c-divider);
      background: var(--c-surface);
    }
    header h1 {
      font-size: 1rem;
      margin: 0;
    }
    .theme-toggle {
      font: inherit;
      border: none;
      background: transparent;
      cursor: pointer;
      color: var(--c-text);
    }
    chat-panel {
      flex: 1;
      min-height: 0;
    }
  `;

  private get panel(): ChatPanel {
    return this.shadowRoot!.querySelector("chat-panel")!;
  }

  private async onSelect(e: Event): Promise<void> {
    const id = (e as CustomEvent).detail.id as string;
    this.activeId = id;
    await this.panel.openThread(id);
  }

  private async onNew(): Promise<void> {
    this.activeId = null;
    await this.panel.openThread(null);
  }

  private async onDelete(e: Event): Promise<void> {
    const id = (e as CustomEvent).detail.id as string;
    await this.threads.remove(id);
    if (this.activeId === id) await this.onNew();
  }

  private async onRename(e: Event): Promise<void> {
    const { id, title } = (e as CustomEvent).detail as {
      id: string;
      title: string;
    };
    await this.threads.rename(id, title);
  }

  private toggleTheme(): void {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
    this.requestUpdate();
  }

  firstUpdated(): void {
    void this.onNew();
  }

  render() {
    return html`
      <thread-sidebar
        .threads=${this.threads.threads}
        .activeId=${this.activeId}
        @select-thread=${this.onSelect}
        @new-thread=${this.onNew}
        @delete-thread=${this.onDelete}
        @rename-thread=${this.onRename}
      ></thread-sidebar>
      <div class="content">
        <header>
          <h1>Concierge</h1>
          <button
            class="theme-toggle"
            aria-label="Toggle theme"
            @click=${this.toggleTheme}
          >
            ${currentTheme() === "dark" ? "☀️" : "🌙"}
          </button>
        </header>
        <chat-panel @turn-finished=${() => void this.threads.refresh()}></chat-panel>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "concierge-app": ConciergeApp;
  }
}
