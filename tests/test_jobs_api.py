import time

import pytest
from fastapi.testclient import TestClient

from app import db, jobs
from app.config import get_settings
from app.extraction.schema import ExtractionError, RecipeDraft
from app.main import create_app
from app.recipes import Ingredient

FOUND = RecipeDraft(found_recipe=True, name="Soup", ingredients=[Ingredient(item="stock")])


def runner(source, on_stage):
    on_stage("Reading your text…")
    if source == "fail":
        raise ExtractionError("No recipe found in that text.")
    return FOUND


@pytest.fixture
def client(tmp_path):
    settings = get_settings(
        {"DATA_DIR": str(tmp_path), "APP_PASSWORD": "pw", "SESSION_SECRET": "s"}
    )
    with TestClient(create_app(settings, runner=runner), follow_redirects=False) as c:
        c.post("/login", data={"password": "pw"})
        yield c


def poll(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_create_and_poll_successful_job(client):
    resp = client.post("/api/jobs", data={"source": "2 cups stock"})
    assert resp.status_code == 201
    body = poll(client, resp.json()["id"])
    assert body["status"] == "done"
    assert body["stage"] == "Reading your text…"
    assert body["error"] is None
    assert body["result"]["name"] == "Soup"
    assert body["result"]["ingredients"][0]["item"] == "stock"


def test_failed_job_reports_message(client):
    job_id = client.post("/api/jobs", data={"source": "fail"}).json()["id"]
    body = poll(client, job_id)
    assert (body["status"], body["error"], body["result"]) == (
        "failed",
        "No recipe found in that text.",
        None,
    )


def test_empty_source_is_rejected(client):
    resp = client.post("/api/jobs", data={"source": "  "})
    assert resp.status_code == 400
    assert "Paste a link" in resp.json()["detail"]


def test_unknown_job_is_404(client):
    assert client.get("/api/jobs/999").status_code == 404


def test_jobs_api_requires_login(tmp_path):
    settings = get_settings({"DATA_DIR": str(tmp_path), "APP_PASSWORD": "pw"})
    with TestClient(create_app(settings, runner=runner)) as c:
        assert c.post("/api/jobs", data={"source": "x"}).status_code == 401
        assert c.get("/api/jobs/1").status_code == 401


def test_startup_fails_jobs_interrupted_by_restart(tmp_path):
    settings = get_settings({"DATA_DIR": str(tmp_path)})
    conn = db.connect(settings.db_path)
    db.migrate(conn)
    stuck = jobs.create_job(conn, "x")
    create_app(settings, runner=runner).state.jobs.stop()
    assert jobs.get_job(conn, stuck).status == "failed"
