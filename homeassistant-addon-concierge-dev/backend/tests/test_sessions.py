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
