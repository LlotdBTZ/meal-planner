"""Shared FastAPI dependencies."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request

from app import db


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """One SQLite connection per request.

    Sync routes run in a thread pool, so sharing one connection would let one
    request's statements land inside another's transaction.
    """
    conn = db.connect(request.app.state.settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


Db = Annotated[sqlite3.Connection, Depends(get_db)]
