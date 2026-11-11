from dataclasses import dataclass
from datetime import date

import psycopg

from backfill_e2e import config

type AggregateKey = tuple[date, str]
type AggregateValue = tuple[int, int, int, int]


@dataclass(frozen=True)
class LedgerRow:
    idx: int
    attempt: int
    status: str
    rows_read: int
    seconds: float


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host="localhost", port=config.PG_PORT, user="backfill", password="backfill", dbname="backfill", autocommit=True
    )


def ground_truth() -> dict[AggregateKey, AggregateValue]:
    with connect() as conn:
        rows = conn.execute(
            "select day, category, event_count, amount_total, amount_min, amount_max from ground_truth"
        ).fetchall()
    return {(r[0], r[1]): (r[2], int(r[3]), r[4], r[5]) for r in rows}


def total_events() -> int:
    with connect() as conn:
        row = conn.execute("select count(*) from events").fetchone()
    assert row is not None
    return row[0]


def aggregates(worker: str) -> dict[AggregateKey, AggregateValue]:
    with connect() as conn:
        rows = conn.execute(
            "select day, category, event_count, amount_total, amount_min, amount_max from daily_aggregates where worker = %s",
            (worker,),
        ).fetchall()
    return {(r[0], r[1]): (r[2], r[3], r[4], r[5]) for r in rows}


def aggregate_run_ids(worker: str) -> set[str]:
    with connect() as conn:
        rows = conn.execute("select distinct run_id from daily_aggregates where worker = %s", (worker,)).fetchall()
    return {r[0] for r in rows}


def ledger(run_id: str) -> list[LedgerRow]:
    with connect() as conn:
        rows = conn.execute(
            "select idx, attempt, status, rows_read, extract(epoch from finished_at - started_at)::float8 "
            "from backfill_ledger where run_id = %s order by idx, attempt, id",
            (run_id,),
        ).fetchall()
    return [LedgerRow(r[0], r[1], r[2], r[3], r[4]) for r in rows]


def reset(worker: str) -> None:
    with connect() as conn:
        conn.execute("delete from daily_aggregates where worker = %s", (worker,))
        conn.execute("delete from backfill_ledger where worker = %s", (worker,))
