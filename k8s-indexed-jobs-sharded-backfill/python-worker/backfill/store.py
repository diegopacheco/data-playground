from dataclasses import dataclass
from datetime import datetime

import psycopg

from backfill.aggregate import Aggregates, aggregate
from backfill.partition import Partition, TimeRange
from backfill.settings import Settings


class TransientFailure(Exception):
    pass


@dataclass(frozen=True)
class Attempt:
    settings: Settings
    partition: Partition
    started_at: datetime


def connect() -> psycopg.Connection:
    return psycopg.connect("", autocommit=True)


def fetch_range(window: TimeRange) -> Aggregates:
    with connect() as conn, conn.cursor() as cur:
        cur.execute(
            "select category, amount_cents from events where ts >= %s and ts < %s",
            (window.start, window.end),
        )
        return aggregate(cur)


def record(conn: psycopg.Connection, attempt: Attempt, status: str, rows_read: int) -> None:
    s = attempt.settings
    conn.execute(
        "insert into backfill_ledger (worker, run_id, idx, day, pod, attempt, status, rows_read, started_at, finished_at) "
        "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())",
        (s.worker, s.run_id, s.index, attempt.partition.day, s.pod, s.attempt, status, rows_read, attempt.started_at),
    )


def write_partition(attempt: Attempt, aggregates: Aggregates, rows_read: int) -> None:
    s = attempt.settings
    day = attempt.partition.day
    with connect() as conn, conn.transaction():
        conn.execute("delete from daily_aggregates where worker = %s and day = %s", (s.worker, day))
        with conn.cursor() as cur:
            cur.executemany(
                "insert into daily_aggregates (worker, day, category, event_count, amount_total, amount_min, amount_max, run_id) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                [(s.worker, day, c, st.count, st.total, st.min, st.max, s.run_id) for c, st in sorted(aggregates.items())],
            )
        if s.must_fail_transiently():
            raise TransientFailure(f"forced transient failure on index {s.index}")
        record(conn, attempt, "ok", rows_read)


def record_failure(attempt: Attempt, status: str) -> None:
    with connect() as conn:
        record(conn, attempt, status, 0)
