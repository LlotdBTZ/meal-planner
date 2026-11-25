"""FastAPI application entry point."""

from __future__ import annotations

from fastapi import FastAPI

from app import db
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Meal Planner", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.db = db.connect(settings.db_path)
    db.migrate(app.state.db)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def run() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(create_app(settings), host="0.0.0.0", port=settings.port, workers=1)


if __name__ == "__main__":
    run()
