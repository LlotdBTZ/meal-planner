from pathlib import Path

from fastapi.testclient import TestClient

from app.config import get_settings, load_dotenv
from app.main import create_app


def test_health_returns_ok(tmp_path):
    client = TestClient(create_app(get_settings({"DATA_DIR": str(tmp_path)})))
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_settings_defaults():
    s = get_settings({})
    assert s.port == 8080
    assert s.data_dir == Path("data")
    assert s.ytdlp_cookies is None
    assert s.db_path == Path("data/meal-planner.db")


def test_settings_from_env():
    s = get_settings(
        {"PORT": "9000", "DATA_DIR": "/var/lib/mp", "YTDLP_COOKIES": "/c.txt", "APP_PASSWORD": "pw"}
    )
    assert s.port == 9000
    assert s.data_dir == Path("/var/lib/mp")
    assert s.ytdlp_cookies == Path("/c.txt")
    assert s.app_password == "pw"


def test_dotenv_does_not_override_existing(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('# comment\nMP_TEST_A="from file"\nMP_TEST_B=file\n')
    monkeypatch.setenv("MP_TEST_B", "real")
    monkeypatch.delenv("MP_TEST_A", raising=False)
    load_dotenv(env_file)
    import os

    assert os.environ["MP_TEST_A"] == "from file"
    assert os.environ["MP_TEST_B"] == "real"


def test_app_creates_and_migrates_database(tmp_path):
    app = create_app(get_settings({"DATA_DIR": str(tmp_path / "d")}))
    assert (tmp_path / "d" / "meal-planner.db").is_file()
    assert app.state.db.execute("PRAGMA user_version").fetchone()[0] >= 1
