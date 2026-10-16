import re
import time
import psycopg
from config import PORTS, DIM, K, M, EF_CONSTRUCTION, BUCKET, BUILD_THREADS
from dataset import literal

SEARCH = f"SELECT id FROM items ORDER BY embedding <-> %s::vector LIMIT {K}"
FILTERED = f"SELECT id FROM items WHERE bucket = {BUCKET} ORDER BY embedding <-> %s::vector LIMIT {K}"


class Pgvector:
    name = "pgvector"
    label = "Postgres pgvector"
    parameters = {"m": "m", "ef_construction": "ef_construction", "ef_search": "SET hnsw.ef_search"}
    deployment = "client/server, psycopg over TCP, vectors sent as text"

    def __init__(self):
        self.con = psycopg.connect(f"postgresql://bench:bench@127.0.0.1:{PORTS['postgres']}/bench", autocommit=True)

    def one(self, sql):
        return self.con.execute(sql).fetchone()[0]

    def version(self):
        self.con.execute("CREATE EXTENSION IF NOT EXISTS vector")
        extension = self.one("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        return f"PostgreSQL {self.one('SHOW server_version').split()[0]}, pgvector {extension}"

    def build(self, vectors, buckets):
        self.con.execute("DROP TABLE IF EXISTS items")
        self.con.execute(f"CREATE TABLE items (id integer PRIMARY KEY, bucket integer NOT NULL, embedding vector({DIM}) NOT NULL)")
        with self.con.cursor() as cur, cur.copy("COPY items (id, bucket, embedding) FROM STDIN") as copy:
            for i, vector in enumerate(vectors):
                copy.write_row((i, int(buckets[i]), literal(vector)))
        self.con.execute("SET maintenance_work_mem = '384MB'")
        self.con.execute(f"SET max_parallel_maintenance_workers = {BUILD_THREADS - 1}")
        started = time.perf_counter()
        self.con.execute(f"CREATE INDEX items_hnsw ON items USING hnsw (embedding vector_l2_ops) WITH (m = {M}, ef_construction = {EF_CONSTRUCTION})")
        seconds = time.perf_counter() - started
        self.con.execute("VACUUM ANALYZE items")
        return {
            "build_seconds": seconds,
            "index_bytes": self.one("SELECT pg_relation_size('items_hnsw')"),
            "index_size_source": "pg_relation_size('items_hnsw')",
            "indexed_rows": self.one("SELECT count(*) FROM items"),
            "state": f"one index, leader plus {BUILD_THREADS - 1} parallel worker",
        }

    def set_ef(self, ef):
        self.con.execute(f"SET hnsw.ef_search = {ef}")

    def search(self, vector):
        return [r[0] for r in self.con.execute(SEARCH, (literal(vector),), prepare=True).fetchall()]

    def filtered_variants(self):
        return [
            ("hnsw.iterative_scan = off", lambda: self.con.execute("SET hnsw.iterative_scan = off")),
            ("hnsw.iterative_scan = strict_order", lambda: self.con.execute("SET hnsw.iterative_scan = strict_order")),
        ]

    def search_filtered(self, vector):
        return [r[0] for r in self.con.execute(FILTERED, (literal(vector),), prepare=True).fetchall()]

    def plan(self, vector, filtered):
        sql = "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF, SUMMARY OFF, BUFFERS OFF) " + (FILTERED if filtered else SEARCH)
        rows = self.con.execute(sql, (literal(vector),)).fetchall()
        return re.sub(r"'\[[^\]]*\]'", "'[query]'", "\n".join(r[0] for r in rows))
