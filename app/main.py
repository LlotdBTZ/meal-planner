"""FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app import db, jobs
from app.auth import Auth, LoginRequired, login_redirect
from app.auth import router as auth_router
from app.config import Settings, get_settings
from app.routes import api, pages
from app.templating import STATIC_DIR

if TYPE_CHECKING:  # the real pipeline imports yt-dlp; load it only when a job runs
    from app.extraction.pipeline import Pipeline
    from app.extraction.schema import RecipeDraft


def _pipeline_runner(settings: Settings) -> jobs.Runner:
    """Build the real pipeline lazily, on the worker thread, at the first job."""
    pipeline: Pipeline | None = None

    def run(source: str, on_stage: Callable[[str], None]) -> RecipeDraft:
        nonlocal pipeline
        if pipeline is None:
            from app.extraction.pipeline import build_pipeline

            pipeline = build_pipeline(settings)
        return pipeline.run(source, on_stage)

    return run


def create_app(settings: Settings | None = None, runner: jobs.Runner | None = None) -> FastAPI:
    settings = settings or get_settings()

    conn = db.connect(settings.db_path)
    db.migrate(conn)
    jobs.recover_interrupted(conn)
    jobs.prune_old_jobs(conn)
    conn.close()

    worker = jobs.JobWorker(settings.db_path, runner or _pipeline_runner(settings))
    worker.start()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        worker.stop()

    app = FastAPI(
        title="Meal Planner", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.settings = settings
    app.state.auth = Auth(settings)
    app.state.jobs = worker

    @app.exception_handler(LoginRequired)
    def _login_required(request: Request, exc: LoginRequired):
        return login_redirect(exc)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(auth_router)
    app.include_router(api.router)
    app.include_router(pages.router)
    return app


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port, workers=1)


if __name__ == "__main__":
    run()
