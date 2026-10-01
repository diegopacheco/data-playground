import sqlite3
from datetime import datetime, timezone

from bytewax.outputs import DynamicSink, StatelessSinkPartition

SCHEMA = """
CREATE TABLE IF NOT EXISTS totals (category TEXT PRIMARY KEY, orders INTEGER, quantity INTEGER, revenue_cents INTEGER, last_order_id INTEGER, updated_at TEXT);
CREATE TABLE IF NOT EXISTS windows (category TEXT, window_start TEXT, orders INTEGER, quantity INTEGER, revenue_cents INTEGER, updated_at TEXT, PRIMARY KEY (category, window_start));
CREATE TABLE IF NOT EXISTS runs (run_id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT, events INTEGER);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


class _Partition(StatelessSinkPartition):
    def __init__(self, path):
        self.conn = connect(path)
        self.run_id = self.conn.execute("INSERT INTO runs (started_at, events) VALUES (?, 0)", (now(),)).lastrowid
        self.conn.commit()

    def write_batch(self, items):
        stamp = now()
        events = 0
        for r in items:
            if r["kind"] == "total":
                events += 1
                self.conn.execute(
                    "INSERT OR REPLACE INTO totals VALUES (?, ?, ?, ?, ?, ?)",
                    (r["category"], r["orders"], r["quantity"], r["revenue_cents"], r["last_order_id"], stamp),
                )
            else:
                self.conn.execute(
                    "INSERT OR REPLACE INTO windows VALUES (?, ?, ?, ?, ?, ?)",
                    (r["category"], r["window_start"], r["orders"], r["quantity"], r["revenue_cents"], stamp),
                )
        self.conn.execute("UPDATE runs SET events = events + ? WHERE run_id = ?", (events, self.run_id))
        self.conn.commit()

    def close(self):
        self.conn.close()


class SqliteSink(DynamicSink):
    def __init__(self, path):
        self.path = path

    def build(self, step_id, worker_index, worker_count):
        return _Partition(self.path)
