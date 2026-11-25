"""SQLite connection and schema migrations.

Migrations are applied in order and tracked with ``PRAGMA user_version``.
Never edit a migration that has shipped; append a new one instead.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

MIGRATIONS: list[str] = [
    # 1: initial schema
    """
    CREATE TABLE recipes (
        id             INTEGER PRIMARY KEY,
        name           TEXT NOT NULL,
        servings       INTEGER,
        source_url     TEXT,
        platform       TEXT,
        thumbnail_path TEXT,
        notes          TEXT,
        steps          TEXT,            -- JSON list of strings
        created_at     TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    );

    CREATE TABLE ingredients (
        id        INTEGER PRIMARY KEY,
        recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
        position  INTEGER NOT NULL,
        quantity  REAL,
        unit      TEXT,
        item      TEXT NOT NULL,
        note      TEXT,
        section   TEXT NOT NULL DEFAULT 'Other',
        raw_text  TEXT
    );
    CREATE INDEX ingredients_recipe ON ingredients(recipe_id, position);

    CREATE TABLE week_selection (
        recipe_id INTEGER PRIMARY KEY REFERENCES recipes(id) ON DELETE CASCADE,
        added_at  TEXT NOT NULL
    );

    CREATE TABLE list_checks (
        item_key TEXT PRIMARY KEY
    );

    CREATE TABLE extraction_jobs (
        id          INTEGER PRIMARY KEY,
        url_or_text TEXT NOT NULL,
        status      TEXT NOT NULL,      -- queued | running | done | failed
        stage       TEXT,
        result_json TEXT,
        error       TEXT,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    """,
]


def connect(path: Path | str) -> sqlite3.Connection:
    """Open the database (creating its folder), with foreign keys and named rows.

    The connection is in autocommit mode; group writes with :func:`transaction`.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run the block in one transaction; roll back if it raises."""
    conn.execute("BEGIN")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def migrate(conn: sqlite3.Connection) -> None:
    """Apply any migrations newer than the database's user_version."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    for version, sql in enumerate(MIGRATIONS, start=1):
        if version <= current:
            continue
        try:
            conn.executescript(f"BEGIN;\n{sql}\n;PRAGMA user_version = {version};\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
