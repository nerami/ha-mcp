from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from concierge.sessions import SessionStore


def make_store(tmp_path: Path) -> SessionStore:
    return SessionStore(tmp_path / "data" / "concierge.db")  # parent dirs created


def test_replace_and_get_messages_roundtrip(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    msgs = [
        {"id": "u1", "role": "user", "content": "hi"},
        {"id": "a1", "role": "assistant", "content": "hello"},
    ]
    store.replace_messages("t1", msgs)
    assert store.get_messages("t1") == msgs
    assert store.get_messages("missing") == []


def test_replace_overwrites_whole_thread(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.replace_messages("t1", [{"id": "u1", "role": "user", "content": "a"}])
    new = [
        {"id": "u1", "role": "user", "content": "a"},
        {"id": "a1", "role": "assistant", "content": "b"},
    ]
    store.replace_messages("t1", new)
    assert store.get_messages("t1") == new


def test_thread_listing_title_and_delete(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.replace_messages("t1", [{"id": "u1", "role": "user", "content": "x"}])
    store.replace_messages("t2", [{"id": "u2", "role": "user", "content": "y"}])
    threads = store.list_threads()
    assert [t["id"] for t in threads] == ["t2", "t1"]  # newest first
    assert threads[0]["title"] is None

    store.set_title("t1", "Lights")
    assert store.get_title("t1") == "Lights"
    assert store.rename_thread("t1", "Lights!") is True
    assert store.rename_thread("nope", "x") is False

    assert store.delete_thread("t1") is True
    assert store.delete_thread("t1") is False
    assert store.get_messages("t1") == []


def test_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "concierge.db"
    SessionStore(path).replace_messages(
        "t1", [{"id": "u1", "role": "user", "content": "x"}]
    )
    assert SessionStore(path).get_messages("t1") != []


def test_concurrent_cross_thread_access_is_safe(tmp_path: Path) -> None:
    # The store shares ONE sqlite3 connection (check_same_thread=False) across
    # threads: reads run in worker threads (asyncio.to_thread) while writes may
    # run on the event-loop thread. Interleave writes/reads/lists from many
    # threads and assert no exception + consistent, well-formed results.
    store = make_store(tmp_path)
    thread_ids = [f"t{i}" for i in range(12)]

    def work(tid: str) -> int:
        for turn in range(20):
            msgs = [
                {"id": f"{tid}-u{turn}", "role": "user", "content": str(turn)},
                {"id": f"{tid}-a{turn}", "role": "assistant", "content": "ok"},
            ]
            store.replace_messages(tid, msgs)
            got = store.get_messages(tid)
            # Whole-thread replace is atomic under the lock: never a partial
            # (odd-length) view, always exactly the two messages we wrote.
            assert len(got) == 2
            store.list_threads()
            store.rename_thread(tid, f"title-{turn}")
        return len(store.get_messages(tid))

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(work, thread_ids))

    assert results == [2] * len(thread_ids)
    # Every thread persisted exactly its final two messages.
    listed = {t["id"] for t in store.list_threads()}
    assert listed == set(thread_ids)
    for tid in thread_ids:
        assert len(store.get_messages(tid)) == 2
