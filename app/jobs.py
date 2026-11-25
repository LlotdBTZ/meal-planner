"""Background extraction jobs.

Extraction can take ~10–60s on the Pi, so the Add page creates a job and polls
it. One worker thread runs jobs one at a time (the Pi has 1GB RAM). The worker
uses its own SQLite connection; WAL mode lets it write while pages read.
"""

from __future__ import annotations

import json
import logging
import queue
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app import db
from app.extraction.schema import ExtractionError, RecipeDraft

log = logging.getLogger(__name__)

MAX_SOURCE_CHARS = 20_000
GENERIC_ERROR = "Something went wrong reading this recipe. Try again, or paste the text instead."
RESTARTED_ERROR = "The app restarted while reading this. Try again."


class JobInputError(ValueError):
    """Bad user input for a new job. The message is plain English, safe to show."""


Runner = Callable[[str, Callable[[str], None]], RecipeDraft]


@dataclass
class Job:
    id: int
    source: str
    status: str  # queued | running | done | failed
    stage: str | None
    result: RecipeDraft | None
    error: str | None
    created_at: str
    updated_at: str


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def create_job(conn: sqlite3.Connection, source: str) -> int:
    source = source.strip()
    if not source:
        raise JobInputError("Paste a link or some recipe text first.")
    if len(source) > MAX_SOURCE_CHARS:
        raise JobInputError("That's too much text. Paste just the recipe part.")
    now = _now()
    cur = conn.execute(
        """INSERT INTO extraction_jobs (url_or_text, status, created_at, updated_at)
           VALUES (?, 'queued', ?, ?)""",
        (source, now, now),
    )
    if cur.lastrowid is None:  # never happens for a plain INSERT; keeps the type honest
        raise RuntimeError("SQLite did not return the new job's id")
    return cur.lastrowid


def get_job(conn: sqlite3.Connection, job_id: int) -> Job | None:
    row = conn.execute("SELECT * FROM extraction_jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    result = RecipeDraft.from_dict(json.loads(row["result_json"])) if row["result_json"] else None
    return Job(
        id=row["id"],
        source=row["url_or_text"],
        status=row["status"],
        stage=row["stage"],
        result=result,
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _update(conn: sqlite3.Connection, job_id: int, **fields: str | None) -> None:
    fields["updated_at"] = _now()
    assignments = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(
        f"UPDATE extraction_jobs SET {assignments} WHERE id = ?", (*fields.values(), job_id)
    )


def recover_interrupted(conn: sqlite3.Connection) -> None:
    """Jobs left queued/running by a restart will never finish; tell the user."""
    conn.execute(
        """UPDATE extraction_jobs SET status = 'failed', error = ?, updated_at = ?
           WHERE status IN ('queued', 'running')""",
        (RESTARTED_ERROR, _now()),
    )


def prune_old_jobs(conn: sqlite3.Connection, days: int = 7) -> None:
    cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
    conn.execute("DELETE FROM extraction_jobs WHERE created_at < ?", (cutoff,))


class JobWorker:
    def __init__(self, db_path: Path, runner: Runner) -> None:
        self.db_path = db_path
        self.runner = runner
        self._queue: queue.Queue[int | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = db.connect(self.db_path)
        return self._conn

    def start(self) -> None:
        if self.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="extraction-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread:
            self._queue.put(None)
            self._thread.join(timeout)

    def is_alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def submit(self, conn: sqlite3.Connection, source: str) -> int:
        job_id = create_job(conn, source)
        self._queue.put(job_id)
        return job_id

    def _loop(self) -> None:
        while (job_id := self._queue.get()) is not None:
            try:
                self.run_job(job_id)
            except Exception:  # never let one bad job kill the worker
                log.exception("Job %s crashed the worker loop", job_id)

    def run_job(self, job_id: int) -> None:
        conn = self.conn
        job = get_job(conn, job_id)
        if job is None:
            return
        _update(conn, job_id, status="running")

        def on_stage(stage: str) -> None:
            _update(conn, job_id, stage=stage)

        try:
            draft = self.runner(job.source, on_stage)
        except ExtractionError as e:
            _update(conn, job_id, status="failed", error=str(e))
        except Exception:
            log.exception("Extraction job %s failed", job_id)
            _update(conn, job_id, status="failed", error=GENERIC_ERROR)
        else:
            _update(conn, job_id, status="done", result_json=json.dumps(draft.to_dict()))
