import { LitElement, css, html } from "lit";
import { customElement } from "lit/decorators.js";

@customElement("concierge-app")
export class ConciergeApp extends LitElement {
  static styles = css`
    :host {
      display: flex;
      height: 100vh;
    }
    main {
      flex: 1;
      display: flex;
      flex-direction: column;
    }
  `;

  render() {
    return html`<main><h1>Concierge</h1></main>`;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "concierge-app": ConciergeApp;
  }
}
