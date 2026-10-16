import re
import time
import duckdb
import numpy as np
from config import DIM, K, M, EF_CONSTRUCTION, BUCKET, BUILD_THREADS
from dataset import literal


class DuckdbVss:
    name = "duckdb-vss"
    label = "DuckDB vss"
    parameters = {"m": "M", "ef_construction": "ef_construction", "ef_search": "SET hnsw_ef_search"}
    deployment = "embedded, in-process, in-memory database"

    def __init__(self):
        self.con = duckdb.connect()
        self.con.load_extension("vss")
        self.con.execute(f"SET threads = {BUILD_THREADS}")

    def version(self):
        vss = self.con.execute("SELECT extension_version FROM duckdb_extensions() WHERE extension_name = 'vss'").fetchone()[0]
        return f"DuckDB {duckdb.__version__}, vss {vss}"

    def build(self, vectors, buckets):
        data = {"id": np.arange(len(vectors), dtype=np.int32), "bucket": buckets}
        data.update({f"c{i}": np.ascontiguousarray(vectors[:, i]) for i in range(DIM)})
        columns = ", ".join(f"c{i}" for i in range(DIM))
        self.con.execute(f"CREATE TABLE items AS SELECT id, bucket, [{columns}]::FLOAT[{DIM}] AS embedding FROM data")
        started = time.perf_counter()
        self.con.execute(f"CREATE INDEX items_hnsw ON items USING HNSW (embedding) WITH (metric = 'l2sq', M = {M}, ef_construction = {EF_CONSTRUCTION})")
        seconds = time.perf_counter() - started
        info = self.con.execute("SELECT count, approx_memory_usage, levels FROM pragma_hnsw_index_info()").fetchone()
        return {
            "build_seconds": seconds,
            "index_bytes": info[1],
            "index_size_source": "approx_memory_usage of pragma_hnsw_index_info()",
            "indexed_rows": info[0],
            "state": f"one in-memory index, {info[2]} graph levels, {BUILD_THREADS} threads",
        }

    def set_ef(self, ef):
        self.con.execute(f"SET hnsw_ef_search = {ef}")

    def sql(self, vector, where=""):
        return f"SELECT id FROM items {where} ORDER BY array_distance(embedding, {literal(vector)}::FLOAT[{DIM}]) LIMIT {K}"

    def search(self, vector):
        return [r[0] for r in self.con.execute(self.sql(vector)).fetchall()]

    def filtered_variants(self):
        return [("WHERE applied after the index scan", lambda: None)]

    def search_filtered(self, vector):
        return [r[0] for r in self.con.execute(self.sql(vector, f"WHERE bucket = {BUCKET}")).fetchall()]

    def plan(self, vector, filtered):
        text = self.con.execute("EXPLAIN " + self.sql(vector, f"WHERE bucket = {BUCKET}" if filtered else "")).fetchall()[0][1]
        return " <- ".join(re.findall(r"│\s+([A-Z_]{4,})\s+│", text))
