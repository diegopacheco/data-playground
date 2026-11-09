import time
from dataclasses import dataclass
from datetime import UTC, datetime

from psycopg import Connection

from loader import store
from loader.config import Settings
from loader.watermark import Watermark


@dataclass(frozen=True)
class PageResult:
    rows: int
    watermark: Watermark


@dataclass(frozen=True)
class RunSummary:
    rows: int
    pages: int
    duration_ms: int
    watermark: Watermark


def load_page(conn: Connection, settings: Settings, until: datetime) -> PageResult:
    with conn.transaction():
        current = store.lock_watermark(conn, settings.job)
        page = store.page_after(conn, current, until, settings.page_size)
        if not page:
            return PageResult(0, current)
        store.upsert(conn, settings.target_table, page)
        time.sleep(settings.hold_before_commit_ms / 1000)
        nxt = current.advance(page)
        store.save_watermark(conn, settings.job, nxt)
        return PageResult(len(page), nxt)


def run(conn: Connection, settings: Settings) -> RunSummary:
    started_at = datetime.now(UTC)
    start = time.monotonic_ns()
    until = store.cutoff(conn, settings.lag_seconds)
    rows = 0
    pages = 0
    page = load_page(conn, settings, until)
    while page.rows > 0:
        rows += page.rows
        pages += 1
        page = load_page(conn, settings, until)
    duration_ms = (time.monotonic_ns() - start) // 1_000_000
    with conn.transaction():
        store.record_run(conn, settings.job, settings.runner, started_at, duration_ms, rows, pages, page.watermark)
    return RunSummary(rows, pages, duration_ms, page.watermark)
