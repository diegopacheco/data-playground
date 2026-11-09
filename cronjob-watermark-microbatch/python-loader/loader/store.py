from datetime import datetime

from psycopg import Connection, sql
from psycopg.rows import class_row

from loader.watermark import Event, Watermark


def cutoff(conn: Connection, lag_seconds: int) -> datetime:
    row = conn.execute("SELECT clock_timestamp() - make_interval(secs => %s)", (float(lag_seconds),)).fetchone()
    if row is None:
        raise RuntimeError("cutoff query returned no row")
    return row[0]


def lock_watermark(conn: Connection, job: str) -> Watermark:
    row = conn.execute(
        "SELECT last_updated_at, last_id FROM watermarks WHERE job = %s FOR UPDATE", (job,)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"no watermark row for job {job}")
    return Watermark(row[0], row[1])


def page_after(conn: Connection, watermark: Watermark, until: datetime, limit: int) -> list[Event]:
    with conn.cursor(row_factory=class_row(Event)) as cur:
        cur.execute(
            """
            SELECT id, account, amount_cents, updated_at
            FROM source_events
            WHERE (updated_at, id) > (%s, %s) AND updated_at <= %s
            ORDER BY updated_at, id
            LIMIT %s
            """,
            (watermark.updated_at, watermark.id, until, limit),
        )
        return cur.fetchall()


def upsert(conn: Connection, table: str, events: list[Event]) -> None:
    query = sql.SQL(
        "INSERT INTO {} (id, account, amount_cents, updated_at) VALUES (%s, %s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET account = EXCLUDED.account, "
        "amount_cents = EXCLUDED.amount_cents, updated_at = EXCLUDED.updated_at"
    ).format(sql.Identifier(table))
    with conn.cursor() as cur:
        cur.executemany(query, [(e.id, e.account, e.amount_cents, e.updated_at) for e in events])


def save_watermark(conn: Connection, job: str, watermark: Watermark) -> None:
    conn.execute(
        "UPDATE watermarks SET last_updated_at = %s, last_id = %s, advanced_at = clock_timestamp() WHERE job = %s",
        (watermark.updated_at, watermark.id, job),
    )


def record_run(
    conn: Connection,
    job: str,
    runner: str,
    started_at: datetime,
    duration_ms: int,
    rows: int,
    pages: int,
    watermark: Watermark,
) -> None:
    conn.execute(
        "INSERT INTO batch_runs (job, runner, started_at, duration_ms, rows_loaded, pages, last_updated_at, last_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (job, runner, started_at, duration_ms, rows, pages, watermark.updated_at, watermark.id),
    )
