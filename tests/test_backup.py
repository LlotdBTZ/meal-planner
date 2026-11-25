import sqlite3
from contextlib import closing
from datetime import date

from app import backup, db


def _make_db(path):
    conn = db.connect(path)
    db.migrate(conn)
    conn.execute(
        "INSERT INTO recipes (name, created_at, updated_at) VALUES ('Tacos', 'now', 'now')"
    )
    conn.commit()
    return conn


def test_backup_copies_database_to_dated_file(tmp_path):
    conn = _make_db(tmp_path / "meal-planner.db")
    out = backup.backup(tmp_path / "meal-planner.db", tmp_path / "backups", date(2026, 11, 24))
    conn.close()

    assert out == tmp_path / "backups" / "meal-planner-2026-11-24.db"
    with closing(sqlite3.connect(out)) as copy:
        assert copy.execute("SELECT name FROM recipes").fetchall() == [("Tacos",)]


def test_backup_is_consistent_while_a_write_is_open(tmp_path):
    conn = _make_db(tmp_path / "meal-planner.db")
    conn.execute("BEGIN")  # db.connect is autocommit; hold a real open transaction
    conn.execute(
        "INSERT INTO recipes (name, created_at, updated_at) VALUES ('Uncommitted', 'now', 'now')"
    )
    out = backup.backup(tmp_path / "meal-planner.db", tmp_path / "backups", date(2026, 11, 24))
    conn.execute("ROLLBACK")

    with closing(sqlite3.connect(out)) as copy:
        names = copy.execute("SELECT name FROM recipes").fetchall()
    conn.close()
    assert names == [("Tacos",)]


def test_backup_same_day_overwrites(tmp_path):
    _make_db(tmp_path / "meal-planner.db").close()
    day = date(2026, 11, 24)
    backup.backup(tmp_path / "meal-planner.db", tmp_path / "backups", day)
    backup.backup(tmp_path / "meal-planner.db", tmp_path / "backups", day)
    assert [p.name for p in (tmp_path / "backups").iterdir()] == ["meal-planner-2026-11-24.db"]


def test_prune_keeps_newest_and_ignores_other_files(tmp_path):
    for day in range(1, 21):
        (tmp_path / f"meal-planner-2026-11-{day:02d}.db").write_text("x")
    (tmp_path / "notes.txt").write_text("keep me")

    removed = backup.prune(tmp_path, keep=14)

    assert sorted(p.name for p in removed) == [
        f"meal-planner-2026-11-{d:02d}.db" for d in range(1, 7)
    ]
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert remaining == [f"meal-planner-2026-11-{d:02d}.db" for d in range(7, 21)] + ["notes.txt"]


def test_main_backs_up_and_prunes_using_data_dir(tmp_path, capsys):
    _make_db(tmp_path / "meal-planner.db").close()
    backups = tmp_path / "backups"
    backups.mkdir()
    for day in range(1, 15):
        (backups / f"meal-planner-2020-01-{day:02d}.db").write_text("old")

    assert backup.main({"DATA_DIR": str(tmp_path)}, today=date(2026, 11, 24)) == 0

    names = sorted(p.name for p in backups.iterdir())
    assert len(names) == 14
    assert names[-1] == "meal-planner-2026-11-24.db"
    assert "meal-planner-2020-01-01.db" not in names
    assert "meal-planner-2026-11-24.db" in capsys.readouterr().out


def test_main_fails_plainly_when_database_missing(tmp_path, capsys):
    assert backup.main({"DATA_DIR": str(tmp_path)}, today=date(2026, 11, 24)) == 1
    assert "No database" in capsys.readouterr().err
    assert not (tmp_path / "backups").exists()
