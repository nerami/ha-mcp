"""SQLite-backed thread/message store on the add-on /data volume.

Messages are opaque AG-UI message dicts (camelCase wire format) stored as
JSON, one row per message. Writes happen once per turn (replace the thread's
messages at stream end) — deliberate, to keep eMMC churn low. WAL mode keeps
a reader (thread list) from blocking the writer.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS threads (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    message_json TEXT NOT NULL,
    PRIMARY KEY (thread_id, seq)
);
"""


class SessionStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        # A single sqlite3 connection is shared across threads
        # (check_same_thread=False): reads run in worker threads via
        # asyncio.to_thread while writes may run on the event-loop thread. A
        # sqlite3 connection is not safe for concurrent use, so serialize every
        # SQL operation under this lock, held for the whole operation.
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def list_threads(self) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, title, created_at, updated_at FROM threads"
                " ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]}
            for r in rows
        ]

    def get_messages(self, thread_id: str) -> list[dict[str, object]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT message_json FROM messages WHERE thread_id = ? ORDER BY seq",
                (thread_id,),
            ).fetchall()
        return [json.loads(r[0]) for r in rows]

    def replace_messages(
        self, thread_id: str, messages: list[dict[str, object]]
    ) -> None:
        now = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO threads (id, title, created_at, updated_at)"
                " VALUES (?, NULL, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at",
                (thread_id, now, now),
            )
            self._conn.execute(
                "DELETE FROM messages WHERE thread_id = ?", (thread_id,)
            )
            self._conn.executemany(
                "INSERT INTO messages (thread_id, seq, message_json)"
                " VALUES (?, ?, ?)",
                [
                    (thread_id, seq, json.dumps(message))
                    for seq, message in enumerate(messages)
                ],
            )

    def get_title(self, thread_id: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT title FROM threads WHERE id = ?", (thread_id,)
            ).fetchone()
        return row[0] if row else None

    def set_title(self, thread_id: str, title: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE threads SET title = ? WHERE id = ?", (title, thread_id)
            )

    def rename_thread(self, thread_id: str, title: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE threads SET title = ? WHERE id = ?", (title, thread_id)
            )
        return cur.rowcount > 0

    def delete_thread(self, thread_id: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute(
                "DELETE FROM threads WHERE id = ?", (thread_id,)
            )
        return cur.rowcount > 0
