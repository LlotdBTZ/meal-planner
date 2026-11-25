import pytest
from fastapi.testclient import TestClient

from app.auth import LoginRateLimiter, safe_next
from app.config import get_settings
from app.main import create_app

PASSWORD = "correct horse"


def make_client(tmp_path, **env):
    settings = get_settings(
        {
            "DATA_DIR": str(tmp_path),
            "APP_PASSWORD": PASSWORD,
            "SESSION_SECRET": "test-secret",
            **env,
        }
    )
    return TestClient(create_app(settings), follow_redirects=False)


@pytest.fixture
def client(tmp_path):
    return make_client(tmp_path)


def login(client, password=PASSWORD, next_="/"):
    return client.post("/login", data={"password": password, "next": next_})


def test_protected_page_redirects_to_login_with_next(client):
    resp = client.get("/add?url=https%3A%2F%2Fwww.tiktok.com%2Fx")
    assert resp.status_code == 303
    assert (
        resp.headers["location"]
        == "/login?next=%2Fadd%3Furl%3Dhttps%253A%252F%252Fwww.tiktok.com%252Fx"
    )


def test_api_without_login_returns_401(client):
    resp = client.get("/api/whoami")
    assert resp.status_code == 401


def test_health_needs_no_login(client):
    assert client.get("/health").status_code == 200


def test_login_page_renders(client):
    resp = client.get("/login?next=/week")
    assert resp.status_code == 200
    assert 'name="password"' in resp.text
    assert 'value="/week"' in resp.text


def test_wrong_password_rejected(client):
    resp = login(client, "nope")
    assert resp.status_code == 401
    assert "Wrong password" in resp.text
    assert "mp_session" not in resp.cookies


def test_right_password_sets_cookie_and_redirects_to_next(client):
    resp = login(client, next_="/week")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/week"
    cookie = resp.headers["set-cookie"]
    assert "mp_session=" in cookie
    assert "HttpOnly" in cookie
    assert "Max-Age=31536000" in cookie
    assert "samesite=lax" in cookie.lower()
    assert client.get("/").status_code == 200
    assert client.get("/api/whoami").json() == {"logged_in": True}


def test_next_must_be_local(client):
    assert login(client, next_="https://evil.example/").headers["location"] == "/"


def test_logout_clears_session(client):
    login(client)
    resp = client.post("/logout")
    assert resp.status_code == 303
    assert client.get("/").status_code == 303


def test_tampered_cookie_rejected(client):
    client.cookies.set("mp_session", "forged.value.here")
    assert client.get("/").status_code == 303


def test_changing_password_logs_everyone_out(tmp_path):
    first = make_client(tmp_path)
    login(first)
    cookie = first.cookies.get("mp_session")
    second = make_client(tmp_path, APP_PASSWORD="new password")
    second.cookies.set("mp_session", cookie)
    assert second.get("/").status_code == 303


def test_no_password_configured_means_no_login(tmp_path):
    client = make_client(tmp_path, APP_PASSWORD="")
    resp = login(client, "")
    assert resp.status_code == 401
    assert "APP_PASSWORD" in resp.text


def test_too_many_failures_are_blocked(client):
    for _ in range(5):
        assert login(client, "nope").status_code == 401
    resp = login(client)  # even the right password, while blocked
    assert resp.status_code == 429


@pytest.mark.parametrize(
    "value, expected",
    [
        ("/week", "/week"),
        ("/add?url=x", "/add?url=x"),
        (None, "/"),
        ("", "/"),
        ("https://evil.example", "/"),
        ("//evil.example", "/"),
        ("/\\evil.example", "/"),
        ("week", "/"),
    ],
)
def test_safe_next(value, expected):
    assert safe_next(value) == expected


def test_rate_limiter_window_expires():
    now = [1000.0]
    limiter = LoginRateLimiter(max_failures=2, window_seconds=60, clock=lambda: now[0])
    limiter.record_failure("ip")
    assert not limiter.is_blocked("ip")
    limiter.record_failure("ip")
    assert limiter.is_blocked("ip")
    assert not limiter.is_blocked("other")
    now[0] += 61
    assert not limiter.is_blocked("ip")
    limiter.record_failure("ip")
    limiter.reset("ip")
    assert not limiter.is_blocked("ip")
