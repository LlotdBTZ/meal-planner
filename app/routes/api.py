"""JSON endpoints used by page JavaScript. All require login (401 otherwise)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from app import jobs
from app.auth import require_login
from app.deps import Db

router = APIRouter(prefix="/api", dependencies=[Depends(require_login)])


@router.get("/whoami")
def whoami() -> dict[str, bool]:
    return {"logged_in": True}


@router.post("/jobs", status_code=201)
def create_job(
    request: Request,
    conn: Db,
    source: str = Form(""),
) -> Any:
    try:
        job_id = request.app.state.jobs.submit(conn, source)
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    return {"id": job_id}


@router.get("/jobs/{job_id}")
def get_job(job_id: int, conn: Db) -> dict[str, Any]:
    job = jobs.get_job(conn, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "status": job.status,
        "stage": job.stage,
        "error": job.error,
        "result": job.result.to_dict() if job.result else None,
    }
