"""App settings, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from a .env file without overriding real env vars."""
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    app_password: str
    session_secret: str
    anthropic_api_key: str
    transcribe_api_key: str
    claude_model: str
    transcribe_model: str
    ytdlp_cookies: Path | None
    data_dir: Path
    port: int

    @property
    def db_path(self) -> Path:
        return self.data_dir / "meal-planner.db"

    @property
    def thumbnails_dir(self) -> Path:
        return self.data_dir / "thumbnails"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"


def get_settings(env: dict[str, str] | None = None) -> Settings:
    """Build settings from `env` (defaults to os.environ, after loading .env)."""
    if env is None:
        load_dotenv(Path(os.environ.get("MEAL_PLANNER_ENV_FILE", ".env")))
        env = dict(os.environ)
    cookies = env.get("YTDLP_COOKIES", "").strip()
    return Settings(
        app_password=env.get("APP_PASSWORD", ""),
        session_secret=env.get("SESSION_SECRET", ""),
        anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
        transcribe_api_key=env.get("TRANSCRIBE_API_KEY", ""),
        claude_model=env.get("CLAUDE_MODEL", "").strip() or "claude-opus-5-5",
        transcribe_model=env.get("TRANSCRIBE_MODEL", "").strip() or "whisper-1",
        ytdlp_cookies=Path(cookies) if cookies else None,
        data_dir=Path(env.get("DATA_DIR", "data")),
        port=int(env.get("PORT", "8080")),
    )
