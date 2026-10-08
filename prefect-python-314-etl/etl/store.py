import os

import psycopg

DDL = """
CREATE TABLE IF NOT EXISTS revenue_by_category (
    category TEXT PRIMARY KEY,
    orders INTEGER NOT NULL,
    units INTEGER NOT NULL,
    revenue NUMERIC(14, 2) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

UPSERT = """
INSERT INTO revenue_by_category (category, orders, units, revenue, loaded_at)
VALUES (%(category)s, %(orders)s, %(units)s, %(revenue)s, now())
ON CONFLICT (category) DO UPDATE
SET orders = EXCLUDED.orders, units = EXCLUDED.units, revenue = EXCLUDED.revenue, loaded_at = EXCLUDED.loaded_at
"""


def connect():
    return psycopg.connect(os.environ["PG_DSN"])


def save(rows):
    with connect() as conn:
        conn.execute(DDL)
        conn.execute("DELETE FROM revenue_by_category WHERE NOT (category = ANY(%s))", ([r["category"] for r in rows],))
        with conn.cursor() as cur:
            cur.executemany(UPSERT, rows)
    return len(rows)


def load_all():
    with connect() as conn:
        conn.execute(DDL)
        cur = conn.execute("SELECT category, orders, units, revenue, loaded_at FROM revenue_by_category ORDER BY category")
        return [
            {"category": c, "orders": o, "units": u, "revenue": str(r), "loaded_at": t.isoformat()}
            for c, o, u, r, t in cur.fetchall()
        ]
