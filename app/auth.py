"""Single-password login with a long-lived signed session cookie (design §6.8).

All auth lives here so real accounts can replace it later without touching pages:
routes depend on :func:`require_login` and nothing else.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections.abc import Callable
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.config import Settings
from app.templating import templates

COOKIE_NAME = "mp_session"
SESSION_MAX_AGE = 365 * 24 * 60 * 60  # one year: log in once per device


class LoginRequired(Exception):
    """Raised by require_login for pages; turned into a redirect to /login."""

    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


def safe_next(value: str | None) -> str:
    """Only allow local paths as post-login redirect targets."""
    if not value or not value.startswith("/") or value.startswith(("//", "/\\")):
        return "/"
    return value


class LoginRateLimiter:
    """Blocks an address after too many failed logins within a time window."""

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: float = 15 * 60,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self.clock = clock
        self._failures: dict[str, list[float]] = {}

    def _recent(self, key: str) -> list[float]:
        cutoff = self.clock() - self.window
        recent = [t for t in self._failures.get(key, []) if t > cutoff]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def is_blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._failures.setdefault(key, []).append(self.clock())

    def reset(self, key: str) -> None:
        self._failures.pop(key, None)


class Auth:
    def __init__(self, settings: Settings) -> None:
        self.password = settings.app_password
        # Without a configured secret, sessions only last until the app restarts.
        secret = settings.session_secret or secrets.token_hex(32)
        self.serializer = URLSafeTimedSerializer(secret, salt="meal-planner-session")
        # Ties sessions to the current password: changing it logs every device out.
        self.fingerprint = hmac.new(
            secret.encode(), self.password.encode(), hashlib.sha256
        ).hexdigest()[:16]
        self.limiter = LoginRateLimiter()

    def check_password(self, candidate: str) -> bool:
        if not self.password:
            return False
        return hmac.compare_digest(candidate.encode(), self.password.encode())

    def make_cookie(self) -> str:
        return self.serializer.dumps({"p": self.fingerprint})

    def is_valid(self, cookie: str | None) -> bool:
        if not cookie:
            return False
        try:
            data = self.serializer.loads(cookie, max_age=SESSION_MAX_AGE)
        except BadSignature:
            return False
        return isinstance(data, dict) and data.get("p") == self.fingerprint


def get_auth(request: Request) -> Auth:
    return request.app.state.auth


def require_login(request: Request) -> None:
    """Dependency for every page/API route except login and health."""
    if get_auth(request).is_valid(request.cookies.get(COOKIE_NAME)):
        return
    if request.url.path.startswith("/api/"):
        raise HTTPException(status_code=401, detail="Not logged in")
    target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    raise LoginRequired(target)


def login_redirect(exc: LoginRequired) -> RedirectResponse:
    return RedirectResponse(f"/login?next={quote(exc.next_path, safe='')}", status_code=303)


router = APIRouter()


def _login_page(request: Request, next_path: str, error: str | None, status: int) -> Response:
    return templates.TemplateResponse(
        request, "login.html", {"next": next_path, "error": error}, status_code=status
    )


@router.get("/login")
def login_form(request: Request, next: str | None = None) -> Response:  # noqa: A002
    return _login_page(request, safe_next(next), None, 200)


@router.post("/login")
def login_submit(
    request: Request,
    password: str = Form(""),
    next: str = Form("/"),  # noqa: A002
) -> Response:
    auth = get_auth(request)
    next_path = safe_next(next)
    client = request.client.host if request.client else "unknown"

    if auth.limiter.is_blocked(client):
        return _login_page(
            request, next_path, "Too many attempts. Try again in a few minutes.", 429
        )
    if not auth.password:
        return _login_page(request, next_path, "APP_PASSWORD isn't set on the server.", 401)
    if not auth.check_password(password):
        auth.limiter.record_failure(client)
        return _login_page(request, next_path, "Wrong password.", 401)

    auth.limiter.reset(client)
    response = RedirectResponse(next_path, status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        auth.make_cookie(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@router.post("/logout")
def logout() -> Response:
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response
