"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from app import db
from app.auth import Auth, LoginRequired, login_redirect
from app.auth import router as auth_router
from app.config import Settings, get_settings
from app.routes import api, pages
from app.templating import STATIC_DIR


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Meal Planner", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.db = db.connect(settings.db_path)
    db.migrate(app.state.db)
    app.state.auth = Auth(settings)

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
