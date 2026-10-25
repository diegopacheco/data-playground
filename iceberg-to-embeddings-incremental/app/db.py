import json
import os

import psycopg

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (
  id bigint PRIMARY KEY,
  category text NOT NULL,
  text text NOT NULL,
  snapshot_id bigint NOT NULL,
  embedding vector(384) NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_state (
  name text PRIMARY KEY,
  snapshot_id bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_rounds (
  round int PRIMARY KEY,
  payload jsonb NOT NULL
);
"""

UPSERT = """
INSERT INTO documents (id, category, text, snapshot_id, embedding) VALUES (%s, %s, %s, %s, %s::vector)
ON CONFLICT (id) DO UPDATE SET category = EXCLUDED.category, text = EXCLUDED.text,
  snapshot_id = EXCLUDED.snapshot_id, embedding = EXCLUDED.embedding
"""

SEARCH = """
SELECT id, category, text, snapshot_id::text AS snapshot_id, 1 - (embedding <=> %(q)s::vector) AS score
FROM documents
ORDER BY embedding <=> %(q)s::vector
LIMIT %(k)s
"""

WATERMARK = "documents"


def connect():
    return psycopg.connect(
        f"host=localhost port={os.environ.get('PGPORT', '30703')} dbname=vectors user=s8 password=s8password",
        autocommit=True,
    )


def init_schema(conn):
    conn.execute(SCHEMA)


def rows(conn, sql, params=None):
    cur = conn.execute(sql, params)
    names = [c.name for c in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def watermark(conn):
    row = conn.execute("SELECT snapshot_id FROM sync_state WHERE name = %s", (WATERMARK,)).fetchone()
    return row[0] if row else None


def set_watermark(conn, snapshot_id):
    conn.execute(
        "INSERT INTO sync_state (name, snapshot_id) VALUES (%s, %s) "
        "ON CONFLICT (name) DO UPDATE SET snapshot_id = EXCLUDED.snapshot_id",
        (WATERMARK, snapshot_id),
    )


def save_round(conn, payload):
    conn.execute("INSERT INTO sync_rounds (round, payload) VALUES (%s, %s)", (payload["round"], json.dumps(payload)))


def rounds(conn):
    return [r[0] for r in conn.execute("SELECT payload FROM sync_rounds ORDER BY round").fetchall()]


def vector_count(conn):
    return conn.execute("SELECT count(*) FROM documents").fetchone()[0]
