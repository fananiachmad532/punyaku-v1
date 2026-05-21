"""SQLite-backed queue + history store.

Thread-safe via a process-wide lock around a single connection. Workers do not
keep the connection open between calls.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from .models import (
    ACTIVE_STATES,
    CANCELED,
    COMPLETED,
    DOWNLOADING,
    FAILED,
    PAUSED,
    PENDING,
    QUEUED,
    QueueItem,
    SKIPPED,
    TERMINAL_STATES,
    WAITING_NET,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT NOT NULL,
    platform        TEXT NOT NULL DEFAULT 'unknown',
    title           TEXT NOT NULL DEFAULT '',
    uploader        TEXT NOT NULL DEFAULT '',
    duration        INTEGER NOT NULL DEFAULT 0,
    upload_date     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL DEFAULT 'pending',
    progress        REAL NOT NULL DEFAULT 0,
    speed           TEXT NOT NULL DEFAULT '',
    eta             TEXT NOT NULL DEFAULT '',
    bytes_downloaded INTEGER NOT NULL DEFAULT 0,
    bytes_total     INTEGER NOT NULL DEFAULT 0,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    priority        INTEGER NOT NULL DEFAULT 100,
    position        INTEGER NOT NULL DEFAULT 0,
    temp_path       TEXT NOT NULL DEFAULT '',
    final_path      TEXT NOT NULL DEFAULT '',
    error           TEXT NOT NULL DEFAULT '',
    options_json    TEXT NOT NULL DEFAULT '',
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    finished_at     REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_queue_status   ON queue_items(status);
CREATE INDEX IF NOT EXISTS idx_queue_priority ON queue_items(priority, position, id);

CREATE TABLE IF NOT EXISTS error_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id    INTEGER,
    ts         REAL NOT NULL,
    level      TEXT NOT NULL,
    message    TEXT NOT NULL
);
"""


class QueueStore:
    """Persistence layer for download queue and history."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init()

    # ---- connection management ----
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=30,
            isolation_level=None,  # autocommit
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _cx(self):  # type: ignore[no-untyped-def]
        with self._lock:
            conn = self._connect()
            try:
                yield conn
            finally:
                conn.close()

    def _init(self) -> None:
        with self._cx() as conn:
            conn.executescript(_SCHEMA)
            # Recover items that were mid-flight on the last shutdown.
            now = time.time()
            conn.execute(
                "UPDATE queue_items SET status=?, updated_at=? WHERE status IN (?, ?)",
                (PENDING, now, DOWNLOADING, WAITING_NET),
            )

    # ---- CRUD ----
    def add_item(self, item: QueueItem) -> int:
        with self._cx() as conn:
            cur = conn.execute(
                """
                INSERT INTO queue_items (
                    url, platform, title, uploader, duration, upload_date,
                    status, progress, speed, eta, bytes_downloaded, bytes_total,
                    retry_count, priority, position, temp_path, final_path,
                    error, options_json, created_at, updated_at, finished_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    item.url, item.platform, item.title, item.uploader,
                    item.duration, item.upload_date, item.status, item.progress,
                    item.speed, item.eta, item.bytes_downloaded, item.bytes_total,
                    item.retry_count, item.priority, item.position, item.temp_path,
                    item.final_path, item.error, item.options_json,
                    item.created_at, item.updated_at, item.finished_at,
                ),
            )
            return int(cur.lastrowid or 0)

    def bulk_add(self, items: Iterable[QueueItem]) -> List[int]:
        ids: List[int] = []
        for it in items:
            ids.append(self.add_item(it))
        return ids

    def get(self, item_id: int) -> Optional[QueueItem]:
        with self._cx() as conn:
            row = conn.execute(
                "SELECT * FROM queue_items WHERE id=?", (item_id,)
            ).fetchone()
        return _row_to_item(row) if row else None

    def all_items(self, statuses: Optional[Sequence[str]] = None) -> List[QueueItem]:
        with self._cx() as conn:
            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                sql = (
                    f"SELECT * FROM queue_items WHERE status IN ({placeholders}) "
                    "ORDER BY priority ASC, position ASC, id ASC"
                )
                rows = conn.execute(sql, list(statuses)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM queue_items ORDER BY priority ASC, position ASC, id ASC"
                ).fetchall()
        return [_row_to_item(r) for r in rows]

    def history(self, limit: int = 500) -> List[QueueItem]:
        with self._cx() as conn:
            rows = conn.execute(
                "SELECT * FROM queue_items WHERE status IN (?, ?, ?, ?) "
                "ORDER BY finished_at DESC LIMIT ?",
                (COMPLETED, FAILED, SKIPPED, CANCELED, limit),
            ).fetchall()
        return [_row_to_item(r) for r in rows]

    def next_runnable(self) -> Optional[QueueItem]:
        """Pop the highest-priority pending/queued/waiting item."""
        with self._cx() as conn:
            row = conn.execute(
                "SELECT * FROM queue_items WHERE status IN (?, ?, ?) "
                "ORDER BY priority ASC, position ASC, id ASC LIMIT 1",
                (PENDING, QUEUED, WAITING_NET),
            ).fetchone()
            if not row:
                return None
            item = _row_to_item(row)
            conn.execute(
                "UPDATE queue_items SET status=?, updated_at=? WHERE id=?",
                (DOWNLOADING, time.time(), item.id),
            )
            item.status = DOWNLOADING
            return item

    def update(self, item_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k}=?" for k in fields)
        with self._cx() as conn:
            conn.execute(
                f"UPDATE queue_items SET {cols} WHERE id=?",
                (*fields.values(), item_id),
            )

    def set_status(self, item_id: int, status: str, error: str = "") -> None:
        now = time.time()
        finished = now if status in TERMINAL_STATES else 0
        with self._cx() as conn:
            conn.execute(
                "UPDATE queue_items SET status=?, error=?, updated_at=?, "
                "finished_at = CASE WHEN ?>0 THEN ? ELSE finished_at END WHERE id=?",
                (status, error, now, finished, finished, item_id),
            )

    def update_progress(
        self,
        item_id: int,
        progress: float,
        speed: str,
        eta: str,
        downloaded: int,
        total: int,
    ) -> None:
        with self._cx() as conn:
            conn.execute(
                "UPDATE queue_items SET progress=?, speed=?, eta=?, "
                "bytes_downloaded=?, bytes_total=?, updated_at=? WHERE id=?",
                (progress, speed, eta, downloaded, total, time.time(), item_id),
            )

    def increment_retry(self, item_id: int) -> int:
        with self._cx() as conn:
            conn.execute(
                "UPDATE queue_items SET retry_count = retry_count + 1, "
                "updated_at=? WHERE id=?",
                (time.time(), item_id),
            )
            row = conn.execute(
                "SELECT retry_count FROM queue_items WHERE id=?", (item_id,)
            ).fetchone()
        return int(row["retry_count"]) if row else 0

    def remove(self, item_id: int) -> None:
        with self._cx() as conn:
            conn.execute("DELETE FROM queue_items WHERE id=?", (item_id,))

    def clear_terminal(self) -> int:
        with self._cx() as conn:
            cur = conn.execute(
                "DELETE FROM queue_items WHERE status IN (?, ?, ?, ?)",
                (COMPLETED, FAILED, SKIPPED, CANCELED),
            )
        return cur.rowcount or 0

    def reorder(self, ordered_ids: Sequence[int]) -> None:
        with self._cx() as conn:
            now = time.time()
            for pos, item_id in enumerate(ordered_ids):
                conn.execute(
                    "UPDATE queue_items SET position=?, updated_at=? WHERE id=?",
                    (pos, now, item_id),
                )

    def pause_all_active(self) -> None:
        now = time.time()
        with self._cx() as conn:
            conn.execute(
                "UPDATE queue_items SET status=?, updated_at=? WHERE status IN (?, ?, ?)",
                (PAUSED, now, PENDING, QUEUED, WAITING_NET),
            )

    def resume_all_paused(self) -> None:
        now = time.time()
        with self._cx() as conn:
            conn.execute(
                "UPDATE queue_items SET status=?, updated_at=? WHERE status=?",
                (PENDING, now, PAUSED),
            )

    # ---- error log ----
    def log_error(self, item_id: Optional[int], message: str, level: str = "ERROR") -> None:
        with self._cx() as conn:
            conn.execute(
                "INSERT INTO error_log (item_id, ts, level, message) VALUES (?,?,?,?)",
                (item_id, time.time(), level, message[:4000]),
            )

    # ---- stats ----
    def stats(self) -> dict:
        with self._cx() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS c FROM queue_items GROUP BY status"
            ).fetchall()
            by_status = {r["status"]: int(r["c"]) for r in rows}
            total = sum(by_status.values())
            active = sum(by_status.get(s, 0) for s in ACTIVE_STATES)
        return {
            "total": total,
            "active": active,
            "completed": by_status.get(COMPLETED, 0),
            "failed": by_status.get(FAILED, 0),
            "skipped": by_status.get(SKIPPED, 0),
            "by_status": by_status,
        }


def _row_to_item(row: sqlite3.Row) -> QueueItem:
    return QueueItem(
        id=row["id"],
        url=row["url"],
        platform=row["platform"],
        title=row["title"],
        uploader=row["uploader"],
        duration=row["duration"],
        upload_date=row["upload_date"],
        status=row["status"],
        progress=row["progress"],
        speed=row["speed"],
        eta=row["eta"],
        bytes_downloaded=row["bytes_downloaded"],
        bytes_total=row["bytes_total"],
        retry_count=row["retry_count"],
        priority=row["priority"],
        position=row["position"],
        temp_path=row["temp_path"],
        final_path=row["final_path"],
        error=row["error"],
        options_json=row["options_json"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row["finished_at"],
    )


def parse_options(item: QueueItem) -> dict:
    if not item.options_json:
        return {}
    try:
        return json.loads(item.options_json)
    except json.JSONDecodeError:
        return {}
