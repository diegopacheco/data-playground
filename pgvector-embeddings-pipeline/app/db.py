import json
import os

import psycopg

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS products (
  id int PRIMARY KEY,
  name text NOT NULL,
  category text NOT NULL,
  description text NOT NULL,
  orders int NOT NULL,
  revenue numeric(12,2) NOT NULL,
  chunks int NOT NULL,
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', name || ' ' || category || ' ' || description)) STORED,
  embedding vector(384) NOT NULL
);
CREATE INDEX IF NOT EXISTS products_embedding_hnsw ON products USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS products_tsv_gin ON products USING gin (tsv);
CREATE INDEX IF NOT EXISTS products_category ON products (category);
CREATE TABLE IF NOT EXISTS variants (
  id int PRIMARY KEY,
  product_id int NOT NULL REFERENCES products(id),
  title text NOT NULL,
  embedding vector(384) NOT NULL
);
CREATE TABLE IF NOT EXISTS pipeline_results (
  id int PRIMARY KEY,
  payload jsonb NOT NULL
);
"""

UPSERT_PRODUCT = """
INSERT INTO products (id, name, category, description, orders, revenue, chunks, embedding)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, category = EXCLUDED.category,
  description = EXCLUDED.description, orders = EXCLUDED.orders, revenue = EXCLUDED.revenue,
  chunks = EXCLUDED.chunks, embedding = EXCLUDED.embedding
"""

UPSERT_VARIANT = """
INSERT INTO variants (id, product_id, title, embedding) VALUES (%s, %s, %s, %s::vector)
ON CONFLICT (id) DO UPDATE SET product_id = EXCLUDED.product_id, title = EXCLUDED.title, embedding = EXCLUDED.embedding
"""

VECTOR_SEARCH = """
SELECT id, name, category, description, 1 - (embedding <=> %(q)s::vector) AS score
FROM products
WHERE %(category)s::text IS NULL OR category = %(category)s
ORDER BY embedding <=> %(q)s::vector
LIMIT %(k)s
"""

HYBRID_SEARCH = """
WITH vec AS (
  SELECT id, 1 - (embedding <=> %(q)s::vector) AS cosine,
         row_number() OVER (ORDER BY embedding <=> %(q)s::vector) AS r
  FROM products
  WHERE %(category)s::text IS NULL OR category = %(category)s
  ORDER BY embedding <=> %(q)s::vector
  LIMIT 20
), txt AS (
  SELECT id, ts_rank(tsv, query) AS rank,
         row_number() OVER (ORDER BY ts_rank(tsv, query) DESC) AS r
  FROM products, to_tsquery('english', replace(plainto_tsquery('english', %(text)s)::text, '&', '|')) query
  WHERE tsv @@ query AND (%(category)s::text IS NULL OR category = %(category)s)
  LIMIT 20
)
SELECT p.id, p.name, p.category, p.description,
       coalesce(1.0 / (60 + vec.r), 0) + coalesce(1.0 / (60 + txt.r), 0) AS score,
       vec.cosine, txt.rank
FROM vec FULL OUTER JOIN txt ON vec.id = txt.id
JOIN products p ON p.id = coalesce(vec.id, txt.id)
ORDER BY score DESC, p.id
LIMIT %(k)s
"""


def dsn():
    return (f"host={os.environ.get('PGHOST', 'localhost')} port={os.environ.get('PGPORT', '24800')} "
            f"dbname=catalog user=catalog password=catalog")


def connect():
    return psycopg.connect(dsn(), autocommit=True)


def init_schema(conn):
    conn.execute(SCHEMA)


def rows(conn, sql, params=None):
    cur = conn.execute(sql, params)
    names = [c.name for c in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def save_results(conn, payload):
    conn.execute("INSERT INTO pipeline_results (id, payload) VALUES (1, %s) "
                 "ON CONFLICT (id) DO UPDATE SET payload = EXCLUDED.payload", (json.dumps(payload),))


def load_results(conn):
    row = conn.execute("SELECT payload FROM pipeline_results WHERE id = 1").fetchone()
    return row[0] if row else None
