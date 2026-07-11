import { expect, it } from "vitest";
import { ThreadsController } from "../src/state/threads-controller";

class FakeHost {
  updates = 0;
  addController(): void {}
  removeController(): void {}
  requestUpdate(): void {
    this.updates++;
  }
  readonly updateComplete = Promise.resolve(true);
}

it("refresh loads threads newest-first as served", async () => {
  const listFn = async () => [
    { id: "t2", title: "B" },
    { id: "t1", title: null },
  ];
  const c = new ThreadsController(new FakeHost() as never, { listFn });
  await c.refresh();
  expect(c.threads.map((t) => t.id)).toEqual(["t2", "t1"]);
  expect(c.loading).toBe(false);
});

it("rename is optimistic then refreshes", async () => {
  let served = [{ id: "t1", title: "old" }];
  const listFn = async () => served;
  const renameFn = async (_id: string, title: string) => {
    served = [{ id: "t1", title }];
  };
  const c = new ThreadsController(new FakeHost() as never, { listFn, renameFn });
  await c.refresh();
  await c.rename("t1", "new");
  expect(c.threads[0]!.title).toBe("new");
});

it("remove deletes then refreshes", async () => {
  let served = [{ id: "t1", title: "x" }];
  const deleteFn = async () => {
    served = [];
  };
  const c = new ThreadsController(new FakeHost() as never, {
    listFn: async () => served,
    deleteFn,
  });
  await c.refresh();
  await c.remove("t1");
  expect(c.threads).toEqual([]);
});

it("captures errors instead of throwing", async () => {
  const c = new ThreadsController(new FakeHost() as never, {
    listFn: async () => {
      throw new Error("down");
    },
  });
  await c.refresh();
  expect(c.error).toBe("down");
  expect(c.loading).toBe(false);
});
