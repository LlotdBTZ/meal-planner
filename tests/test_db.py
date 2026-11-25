import sqlite3

import pytest

from app import db


def test_migrate_creates_tables_and_sets_version(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn)
    tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "recipes",
        "ingredients",
        "week_selection",
        "list_checks",
        "extraction_jobs",
    } <= tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)


def test_migrate_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    db.migrate(conn)
    db.migrate(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)


def test_connect_enables_foreign_keys_and_creates_parent_dir(tmp_path):
    conn = db.connect(tmp_path / "nested" / "dir" / "t.db")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert (tmp_path / "nested" / "dir").is_dir()


def test_rows_are_accessible_by_name(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    assert isinstance(conn.execute("SELECT 1 AS one").fetchone(), sqlite3.Row)


def test_failed_migration_rolls_back(tmp_path, monkeypatch):
    conn = db.connect(tmp_path / "t.db")
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, "CREATE TABLE x (a); SELECT nope();"])
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(conn)
    names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "x" not in names
    assert conn.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS) - 1
