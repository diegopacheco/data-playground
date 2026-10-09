import os
import time

import psycopg

import s3

DSN = os.environ.get("PG_DSN", "host=localhost port=27600 user=postgres dbname=postgres")
DATA = os.environ.get("DATA_DIR", "/data")
BUCKET = os.environ.get("LAKE_BUCKET", "lake")
RAW = f"s3://{BUCKET}/raw/orders"
BATCHES = (1, 2)

REVENUE_SQL = """SELECT c.country, count(*) AS orders, sum(o.quantity) AS units, sum(o.quantity * o.price) AS revenue
FROM orders o JOIN customers c ON c.customer_id = o.customer_id
GROUP BY c.country ORDER BY revenue DESC, c.country"""

MONTHLY_SQL = """SELECT to_char(order_date, 'YYYY-MM') AS month, status, count(*) AS orders, sum(quantity * price) AS revenue
FROM orders GROUP BY 1, 2 ORDER BY 1, 2"""

RAW_SQL = """SELECT _filename AS file, count(*) AS orders, sum(quantity * price) AS revenue
FROM raw_orders GROUP BY 1 ORDER BY 1"""

AUGUST_SQL = """SELECT count(*) AS orders FROM orders WHERE order_date >= '2026-08-01'"""


class LakeError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def connect():
    return psycopg.connect(DSN, autocommit=True)


def rows(cur, sql, params=None):
    cur.execute(sql, params)
    names = [d.name for d in cur.description]
    return [dict(zip(names, [plain(v) for v in r])) for r in cur.fetchall()]


def plain(v):
    if hasattr(v, "is_finite"):
        return str(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def timed(cur, sql):
    start = time.perf_counter()
    result = rows(cur, sql)
    return result, round((time.perf_counter() - start) * 1000, 1)


def explain(cur, sql):
    cur.execute("EXPLAIN (VERBOSE) " + sql)
    return "\n".join(r[0] for r in cur.fetchall())


def table_exists(cur, name):
    cur.execute("SELECT to_regclass(%s) IS NOT NULL", (name,))
    return cur.fetchone()[0]


def reset():
    s3.ensure_bucket(BUCKET)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS pg_lake CASCADE")
        cur.execute("DROP FOREIGN TABLE IF EXISTS raw_orders")
        cur.execute("DROP TABLE IF EXISTS orders, orders_landing, customers")
        removed = s3.delete_prefix(BUCKET, "raw/") + s3.delete_prefix(BUCKET, "iceberg/")
        cur.execute("CREATE TABLE customers (customer_id int PRIMARY KEY, name text NOT NULL, country text NOT NULL, tier text NOT NULL)")
        copy_csv(cur, "customers", "customers.csv")
        cur.execute("CREATE UNLOGGED TABLE orders_landing (order_id bigint, customer_id int, product text, quantity int, price numeric(10,2), status text, order_date date)")
        cur.execute("CREATE TABLE orders (order_id bigint NOT NULL, customer_id int NOT NULL, product text, quantity int, price numeric(10,2), status text, order_date date) USING iceberg WITH (partition_by = 'month(order_date)')")
        cur.execute("SELECT count(*) FROM customers")
        return {"customers": cur.fetchone()[0], "removedObjects": removed}


def copy_csv(cur, table, name):
    with open(os.path.join(DATA, name), "rb") as f, cur.copy(f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true)") as copy:
        while chunk := f.read(65536):
            copy.write(chunk)


def load(batch):
    if batch not in BATCHES:
        raise LakeError(400, f"batch must be one of {list(BATCHES)}")
    target = f"{RAW}/batch-{batch}.parquet"
    with connect() as conn, conn.cursor() as cur:
        if not table_exists(cur, "orders"):
            raise LakeError(409, "tables missing, call POST /api/reset first")
        if any(o["key"] == f"raw/orders/batch-{batch}.parquet" for o in s3.list_objects(BUCKET, "raw/orders/")):
            raise LakeError(409, f"batch {batch} is already in the lake")
        steps = []
        start = time.perf_counter()
        cur.execute("TRUNCATE orders_landing")
        copy_csv(cur, "orders_landing", f"orders-batch-{batch}.csv")
        steps.append(step("csv into heap landing table", "COPY orders_landing FROM STDIN (csv)", start))
        start = time.perf_counter()
        cur.execute(f"COPY orders_landing TO '{target}'")
        steps.append(step("heap table exported as Parquet to MinIO", f"COPY orders_landing TO '{target}'", start))
        start = time.perf_counter()
        if not table_exists(cur, "raw_orders"):
            cur.execute(f"CREATE FOREIGN TABLE raw_orders () SERVER pg_lake OPTIONS (path '{RAW}/*.parquet', filename 'true')")
        insert = f"INSERT INTO orders SELECT order_id, customer_id, product, quantity, price, status, order_date FROM raw_orders WHERE _filename = '{target}'"
        cur.execute(insert)
        inserted = cur.rowcount
        steps.append(step("Parquet read back and written into the Iceberg table", insert, start))
        cur.execute("TRUNCATE orders_landing")
        return {"batch": batch, "file": target, "inserted": inserted, "steps": steps}


def step(name, sql, start):
    return {"name": name, "sql": sql, "ms": round((time.perf_counter() - start) * 1000, 1)}


def delete_cancelled():
    with connect() as conn, conn.cursor() as cur:
        if not table_exists(cur, "orders"):
            raise LakeError(409, "tables missing, call POST /api/reset first")
        cur.execute("DELETE FROM orders WHERE status = 'cancelled'")
        return {"deleted": cur.rowcount}


def run():
    result = {"reset": reset(), "loads": [load(b) for b in BATCHES]}
    result["delete"] = delete_cancelled()
    return result


def status():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        extensions = rows(cur, "SELECT extname AS name, extversion AS version FROM pg_extension WHERE extname LIKE 'pg_lake%' OR extname LIKE 'pg_extension%' OR extname = 'pg_map' ORDER BY 1")
        tables = rows(cur, """SELECT c.relname AS name,
            CASE c.relkind WHEN 'r' THEN 'heap' WHEN 'f' THEN s.srvname END AS storage,
            c.relpersistence = 'u' AS unlogged
            FROM pg_class c
            LEFT JOIN pg_foreign_table ft ON ft.ftrelid = c.oid
            LEFT JOIN pg_foreign_server s ON s.oid = ft.ftserver
            WHERE c.relnamespace = 'public'::regnamespace AND c.relkind IN ('r', 'f') ORDER BY 1""")
        for t in tables:
            cur.execute(f'SELECT count(*) FROM "{t["name"]}"')
            t["rows"] = cur.fetchone()[0]
        return {"postgres": version, "extensions": extensions, "tables": tables, "bucket": BUCKET}


def query(name):
    sql = {"revenue": REVENUE_SQL, "monthly": MONTHLY_SQL, "raw": RAW_SQL, "august": AUGUST_SQL}.get(name)
    if sql is None:
        raise LakeError(404, f"unknown query {name}")
    with connect() as conn, conn.cursor() as cur:
        needed = "raw_orders" if name == "raw" else "orders"
        if not table_exists(cur, needed):
            raise LakeError(409, f"{needed} missing, run the pipeline first")
        result, ms = timed(cur, sql)
        plan = explain(cur, sql)
        return {"name": name, "sql": sql, "rows": result, "ms": ms, "plan": plan, "pushdown": "Custom Scan (Query Pushdown)" in plan, "engine": "Engine: DuckDB" in plan}


def lake():
    with connect() as conn, conn.cursor() as cur:
        tables = rows(cur, "SELECT catalog_name, table_namespace, table_name, metadata_location FROM iceberg_tables ORDER BY table_name") if table_exists(cur, "iceberg_tables") else []
        snapshots, files = [], []
        if any(t["table_name"] == "orders" for t in tables):
            location = next(t["metadata_location"] for t in tables if t["table_name"] == "orders")
            cur.execute("SELECT lake_iceberg.metadata(%s)", (location,))
            meta = cur.fetchone()[0]
            for s in sorted(meta.get("snapshots", []), key=lambda s: s.get("sequence-number", 0)):
                snapshots.append({"id": str(s["snapshot-id"]), "sequence": s.get("sequence-number"), "timestamp": s["timestamp-ms"], "operation": s.get("summary", {}).get("operation"), "manifestList": s.get("manifest-list")})
            current = str(meta.get("current-snapshot-id"))
            files = rows(cur, "SELECT content, file_path, file_format, record_count, file_size_in_bytes FROM lake_iceberg.files(%s) ORDER BY file_path", (location,))
            partitions = meta.get("partition-specs", [])
        else:
            current, partitions = None, []
    objects = s3.list_objects(BUCKET)
    return {"bucket": BUCKET, "tables": tables, "snapshots": snapshots, "currentSnapshot": current, "partitionSpecs": partitions, "files": files, "objects": objects}
