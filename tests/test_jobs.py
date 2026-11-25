import threading
import time

import pytest

from app import db, jobs
from app.extraction.schema import ExtractionError, RecipeDraft
from app.recipes import Ingredient

FOUND = RecipeDraft(found_recipe=True, name="Soup", ingredients=[Ingredient(item="stock")])


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    db.migrate(conn)
    conn.close()
    return path


@pytest.fixture
def conn(db_path):
    c = db.connect(db_path)
    yield c
    c.close()


def ok_runner(source, on_stage):
    on_stage("Reading the caption…")
    return RecipeDraft.from_dict(FOUND.to_dict())


def test_create_and_get(conn):
    jid = jobs.create_job(conn, "https://www.tiktok.com/x")
    job = jobs.get_job(conn, jid)
    assert (job.id, job.status, job.stage, job.result, job.error) == (
        jid,
        "queued",
        None,
        None,
        None,
    )
    assert job.source == "https://www.tiktok.com/x"
    assert jobs.get_job(conn, 999) is None


def test_create_rejects_empty_and_huge_input(conn):
    with pytest.raises(ValueError):
        jobs.create_job(conn, "  ")
    with pytest.raises(ValueError):
        jobs.create_job(conn, "x" * (jobs.MAX_SOURCE_CHARS + 1))


def test_run_job_success_records_stage_and_result(db_path, conn):
    worker = jobs.JobWorker(db_path, ok_runner)
    jid = jobs.create_job(conn, "https://www.tiktok.com/x")
    worker.run_job(jid)
    job = jobs.get_job(conn, jid)
    assert job.status == "done"
    assert job.stage == "Reading the caption…"
    assert job.result == FOUND
    assert job.error is None


def test_stage_is_visible_while_running(db_path, conn):
    seen = []

    def runner(source, on_stage):
        on_stage("Listening to the video…")
        seen.append(jobs.get_job(conn, jid))
        return FOUND

    jid = jobs.create_job(conn, "x")
    jobs.JobWorker(db_path, runner).run_job(jid)
    assert seen[0].status == "running"
    assert seen[0].stage == "Listening to the video…"


def test_extraction_error_message_is_recorded(db_path, conn):
    def runner(source, on_stage):
        raise ExtractionError("This post needs a login.")

    jid = jobs.create_job(conn, "x")
    jobs.JobWorker(db_path, runner).run_job(jid)
    job = jobs.get_job(conn, jid)
    assert (job.status, job.error, job.result) == ("failed", "This post needs a login.", None)


def test_unexpected_error_gets_generic_message(db_path, conn):
    def runner(source, on_stage):
        raise RuntimeError("secret internals")

    jid = jobs.create_job(conn, "x")
    jobs.JobWorker(db_path, runner).run_job(jid)
    job = jobs.get_job(conn, jid)
    assert job.status == "failed"
    assert "secret" not in job.error
    assert "went wrong" in job.error


def test_recover_marks_unfinished_jobs_failed(conn):
    queued = jobs.create_job(conn, "a")
    running = jobs.create_job(conn, "b")
    conn.execute("UPDATE extraction_jobs SET status='running' WHERE id=?", (running,))
    done = jobs.create_job(conn, "c")
    conn.execute("UPDATE extraction_jobs SET status='done' WHERE id=?", (done,))
    jobs.recover_interrupted(conn)
    assert jobs.get_job(conn, queued).status == "failed"
    assert "restarted" in jobs.get_job(conn, running).error
    assert jobs.get_job(conn, done).status == "done"


def test_prune_old_jobs(conn):
    old = jobs.create_job(conn, "old")
    conn.execute(
        "UPDATE extraction_jobs SET created_at='2000-01-01T00:00:00+00:00' WHERE id=?", (old,)
    )
    new = jobs.create_job(conn, "new")
    jobs.prune_old_jobs(conn, days=7)
    assert jobs.get_job(conn, old) is None
    assert jobs.get_job(conn, new) is not None


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_worker_thread_processes_jobs_one_at_a_time(db_path, conn):
    active, max_active, lock = [0], [0], threading.Lock()

    def runner(source, on_stage):
        with lock:
            active[0] += 1
            max_active[0] = max(max_active[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return FOUND

    worker = jobs.JobWorker(db_path, runner)
    worker.start()
    try:
        ids = [worker.submit(conn, f"https://x/{i}") for i in range(3)]
        assert wait_for(lambda: all(jobs.get_job(conn, i).status == "done" for i in ids))
        assert max_active[0] == 1
    finally:
        worker.stop()
    assert not worker.is_alive()


def test_worker_survives_a_crashing_job(db_path, conn):
    calls = []

    def runner(source, on_stage):
        calls.append(source)
        if source == "boom":
            raise RuntimeError("x")
        return FOUND

    worker = jobs.JobWorker(db_path, runner)
    worker.start()
    try:
        bad = worker.submit(conn, "boom")
        good = worker.submit(conn, "fine")
        assert wait_for(lambda: jobs.get_job(conn, good).status == "done")
        assert jobs.get_job(conn, bad).status == "failed"
    finally:
        worker.stop()


def test_stop_closes_the_worker_connection(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    db.migrate(conn)
    worker = jobs.JobWorker(path, lambda source, on_stage: None)
    worker.start()
    worker.submit(conn, "hello")
    worker.stop()
    conn.close()
    assert worker._conn is None
