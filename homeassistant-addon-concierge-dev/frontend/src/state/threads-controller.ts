import type { ReactiveController, ReactiveControllerHost } from "lit";
import {
  deleteThread,
  listThreads,
  renameThread,
  type ThreadMeta,
} from "../agui/api";

type Opts = {
  listFn?: () => Promise<ThreadMeta[]>;
  renameFn?: (id: string, title: string) => Promise<void>;
  deleteFn?: (id: string) => Promise<void>;
};

export class ThreadsController implements ReactiveController {
  threads: ThreadMeta[] = [];
  loading = false;
  error: string | null = null;

  private host: ReactiveControllerHost;
  private listFn: () => Promise<ThreadMeta[]>;
  private renameFn: (id: string, title: string) => Promise<void>;
  private deleteFn: (id: string) => Promise<void>;

  constructor(host: ReactiveControllerHost, opts: Opts = {}) {
    this.host = host;
    this.listFn = opts.listFn ?? (() => listThreads());
    this.renameFn = opts.renameFn ?? ((id, title) => renameThread(id, title));
    this.deleteFn = opts.deleteFn ?? ((id) => deleteThread(id));
    host.addController(this);
  }

  hostConnected(): void {
    void this.refresh();
  }
  hostDisconnected(): void {}

  async refresh(): Promise<void> {
    this.loading = true;
    this.error = null;
    this.host.requestUpdate();
    try {
      this.threads = await this.listFn();
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    } finally {
      this.loading = false;
      this.host.requestUpdate();
    }
  }

  async rename(id: string, title: string): Promise<void> {
    this.threads = this.threads.map((t) => (t.id === id ? { ...t, title } : t));
    this.host.requestUpdate();
    try {
      await this.renameFn(id, title);
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    }
    await this.refresh();
  }

  async remove(id: string): Promise<void> {
    try {
      await this.deleteFn(id);
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    }
    await this.refresh();
  }
}
