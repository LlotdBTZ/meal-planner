"""JSON endpoints used by page JavaScript. All require login (401 otherwise)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_login

router = APIRouter(prefix="/api", dependencies=[Depends(require_login)])


@router.get("/whoami")
def whoami() -> dict[str, bool]:
    return {"logged_in": True}
