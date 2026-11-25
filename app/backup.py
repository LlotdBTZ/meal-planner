"""Nightly SQLite backup: copy the database to a dated file and keep the newest few.

Run with ``python -m app.backup`` (the systemd backup timer does this). Uses
SQLite's online backup API, so it is safe while the app is running.
"""

from __future__ import annotations

import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

from app.config import get_settings

KEEP = 14
_NAME = re.compile(r"^meal-planner-\d{4}-\d{2}-\d{2}\.db$")


def backup(db_path: Path, backup_dir: Path, today: date) -> Path:
    """Copy `db_path` to `backup_dir/meal-planner-YYYY-MM-DD.db` and return that path."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"meal-planner-{today.isoformat()}.db"
    tmp = dest.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out = sqlite3.connect(tmp)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    tmp.replace(dest)
    return dest


def prune(backup_dir: Path, keep: int = KEEP) -> list[Path]:
    """Delete all but the newest `keep` dated backups. Other files are left alone."""
    dated = sorted(p for p in backup_dir.iterdir() if _NAME.match(p.name))
    old = dated[:-keep] if keep > 0 else dated
    for p in old:
        p.unlink()
    return old


def main(env: dict[str, str] | None = None, today: date | None = None) -> int:
    settings = get_settings(env)
    if not settings.db_path.is_file():
        print(f"No database at {settings.db_path}; nothing to back up.", file=sys.stderr)
        return 1
    backup_dir = settings.data_dir / "backups"
    dest = backup(settings.db_path, backup_dir, today or date.today())
    removed = prune(backup_dir)
    print(f"Backed up to {dest}; removed {len(removed)} old backup(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
