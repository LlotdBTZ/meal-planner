"""Shared test setup."""

import pytest

from app import db


@pytest.fixture(autouse=True)
def _close_db_connections(monkeypatch):
    """Close every connection a test opened through db.connect when it ends.

    Unclosed connections only warn (ResourceWarning), and the warnings are
    turned into errors in pyproject.toml so a real leak in app code shows up.
    """
    opened = []
    real_connect = db.connect

    def tracking_connect(path):
        conn = real_connect(path)
        opened.append(conn)
        return conn

    monkeypatch.setattr(db, "connect", tracking_connect)
    yield
    for conn in opened:
        conn.close()
