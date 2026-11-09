import time
from collections.abc import Iterator

import pytest
from psycopg import Connection, sql

from cluster import (
    backend_state,
    connect,
    consistency,
    cron_runs_with_rows,
    fingerprint,
    generator_gone,
    kill_job,
    last_run,
    loader_pods_running,
    run_job,
    scale_generator,
    start_job,
    suspend_cronjobs,
    table,
    wait_for,
    watermark,
)

JOBS = ["java", "python"]
LAG_SECONDS = 2


@pytest.fixture(scope="module")
def conn() -> Iterator[Connection]:
    with connect() as c:
        yield c


@pytest.fixture(scope="module")
def quiet(conn: Connection) -> Iterator[Connection]:
    suspend_cronjobs(True)
    scale_generator(0)
    try:
        wait_for("generator to stop", generator_gone, 60)
        wait_for("scheduled loader pods to finish", lambda: not loader_pods_running(), 180)
        time.sleep(LAG_SECONDS + 1)
        yield conn
    finally:
        suspend_cronjobs(False)
        scale_generator(1)


def assert_consistent(conn: Connection, job: str) -> None:
    c = consistency(conn, job)
    assert c.missing == 0, f"{job}: {c.missing} source rows up to the watermark are not in the target (gap)"
    assert c.orphan == 0, f"{job}: {c.orphan} target rows do not exist in source"
    assert c.ahead == 0, f"{job}: {c.ahead} target rows are past the watermark, load and watermark were not atomic"
    assert c.expected > 0


def add_rows(conn: Connection, count: int, account: str) -> None:
    conn.execute(
        "INSERT INTO source_events (account, amount_cents, updated_at) SELECT %s, g, now() FROM generate_series(1, %s) g",
        (account, count),
    )
    time.sleep(LAG_SECONDS + 1)


@pytest.mark.parametrize("job", JOBS)
def test_scheduled_cronjobs_load_live_inserts_with_no_gaps_and_no_duplicates(conn: Connection, job: str) -> None:
    wait_for(f"two scheduled {job} batches with rows", lambda: cron_runs_with_rows(conn, job) >= 2, 240)
    assert_consistent(conn, job)


@pytest.mark.parametrize("job", JOBS)
def test_rerun_and_full_replay_change_nothing(quiet: Connection, job: str) -> None:
    run_job(job)
    before_fp = fingerprint(quiet, job)
    before_wm = watermark(quiet, job)

    name = run_job(job)
    assert last_run(quiet, name).rows_loaded == 0
    assert fingerprint(quiet, job) == before_fp
    assert watermark(quiet, job) == before_wm

    quiet.execute("UPDATE watermarks SET last_updated_at = '1970-01-01Z', last_id = 0 WHERE job = %s", (job,))
    name = run_job(job)
    assert last_run(quiet, name).rows_loaded == before_fp.rows, "replay must re-read every row"
    assert fingerprint(quiet, job) == before_fp, "replaying every row must not duplicate or alter the target"
    assert watermark(quiet, job) == before_wm
    assert_consistent(quiet, job)


@pytest.mark.parametrize("job", JOBS)
def test_killed_batch_keeps_watermark_and_next_run_catches_up(quiet: Connection, job: str) -> None:
    run_job(job)
    add_rows(quiet, 300, f"kill-{job}")
    before_fp = fingerprint(quiet, job)
    before_wm = watermark(quiet, job)

    name = start_job(job, {"HOLD_BEFORE_COMMIT_MS": "300000"})
    wait_for(f"{job} batch to sit inside its transaction", lambda: "idle in transaction" in backend_state(quiet, job), 120)
    assert fingerprint(quiet, job) == before_fp, "uncommitted rows must not be visible"
    kill_job(name)
    wait_for(f"postgres to roll back the killed {job} batch", lambda: backend_state(quiet, job) == [], 60)
    assert watermark(quiet, job) == before_wm, "killed batch must not advance the watermark"
    assert fingerprint(quiet, job) == before_fp, "killed batch must leave no partial rows"

    name = run_job(job)
    assert last_run(quiet, name).rows_loaded == 300
    assert fingerprint(quiet, job).rows == before_fp.rows + 300
    assert watermark(quiet, job) > before_wm
    assert_consistent(quiet, job)


@pytest.mark.parametrize("job", JOBS)
def test_late_rows_with_the_watermark_timestamp_are_not_lost_across_pages(quiet: Connection, job: str) -> None:
    run_job(job)
    ts, last_id = watermark(quiet, job)
    quiet.execute(
        "INSERT INTO source_events (account, amount_cents, updated_at) SELECT %s, g, %s FROM generate_series(1, 1200) g",
        (f"late-{job}", ts),
    )

    name = run_job(job)
    run = last_run(quiet, name)
    assert run.rows_loaded == 1200
    assert run.pages == 3, "1200 tied rows with page size 500 must be paged by id inside one timestamp"
    late = quiet.execute(
        sql.SQL("SELECT count(*) FROM {} WHERE account = %s AND updated_at = %s AND id > %s").format(table(job)),
        (f"late-{job}", ts, last_id),
    ).fetchone()
    assert late is not None and late[0] == 1200
    assert watermark(quiet, job)[0] == ts
    assert_consistent(quiet, job)
