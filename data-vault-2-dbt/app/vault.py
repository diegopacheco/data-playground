import os
import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("VAULT_DB", os.path.join(ROOT, ".run", "vault.duckdb"))
DATA = os.path.join(ROOT, "data")


def load_dates():
    return sorted(d for d in os.listdir(DATA) if os.path.isdir(os.path.join(DATA, d)))


def connect():
    return duckdb.connect(DB, read_only=True)


def rows(con, sql, params=None):
    cur = con.execute(sql, params or [])
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]
