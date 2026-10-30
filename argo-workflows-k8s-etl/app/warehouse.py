import os
import psycopg
from psycopg.rows import dict_row


def connect():
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row, connect_timeout=5)


def load(batch, seed, rows, report):
    with connect() as conn:
        conn.execute("DELETE FROM region_totals WHERE batch = %s", (batch,))
        conn.execute(
            "INSERT INTO batches (batch, seed, rows, orders, cents) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (batch) DO UPDATE SET seed = EXCLUDED.seed, rows = EXCLUDED.rows, "
            "orders = EXCLUDED.orders, cents = EXCLUDED.cents, loaded_at = now()",
            (batch, seed, rows, report["orders"], report["cents"]),
        )
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO region_totals (batch, region, orders, cents, max_cents, big_orders, days) "
                "VALUES (%(batch)s, %(region)s, %(orders)s, %(cents)s, %(max_cents)s, %(big_orders)s, %(days)s)",
                [dict(r, batch=batch) for r in report["regions"]],
            )


def alert(batch, threshold, hot):
    with connect() as conn:
        conn.execute("DELETE FROM alerts WHERE batch = %s", (batch,))
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO alerts (batch, region, cents, threshold) VALUES (%s, %s, %s, %s)",
                [(batch, r["region"], r["cents"], threshold) for r in hot],
            )


def batches(limit=20):
    with connect() as conn:
        return conn.execute(
            "SELECT batch, seed, rows, orders, cents, to_char(loaded_at, 'YYYY-MM-DD HH24:MI:SS') AS loaded_at "
            "FROM batches ORDER BY loaded_at DESC LIMIT %s",
            (limit,),
        ).fetchall()


def batch_detail(batch):
    with connect() as conn:
        regions = conn.execute(
            "SELECT region, orders, cents, max_cents, big_orders, days FROM region_totals WHERE batch = %s ORDER BY region",
            (batch,),
        ).fetchall()
        alerts = conn.execute(
            "SELECT region, cents, threshold FROM alerts WHERE batch = %s ORDER BY region", (batch,)
        ).fetchall()
    return {"batch": batch, "regions": regions, "alerts": alerts}
