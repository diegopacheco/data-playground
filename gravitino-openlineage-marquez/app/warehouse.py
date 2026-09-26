import os
import psycopg

PG_DSN = os.environ.get("PG_DSN", "postgresql://shop:shop@localhost:27103/shop")
ORDERS = os.path.join(os.path.dirname(__file__), "..", "data", "orders.csv")
CSV_COLUMNS = "order_id, customer, product, category, quantity, price, ts"

LOAD_RAW_SQL = f"TRUNCATE raw.raw_orders;\nCOPY raw.raw_orders ({CSV_COLUMNS}) FROM STDIN WITH (FORMAT csv, HEADER true)"

BUILD_CLEAN_SQL = """TRUNCATE clean.clean_orders;
INSERT INTO clean.clean_orders (order_id, customer_hash, product, category, quantity, price, amount, ts)
SELECT order_id,
       encode(sha256(convert_to(lower(trim(customer)), 'UTF8')), 'hex'),
       trim(product),
       lower(trim(category)),
       quantity,
       price,
       quantity * price,
       ts
FROM raw.raw_orders
WHERE quantity > 0 AND price > 0"""

BUILD_REVENUE_SQL = """TRUNCATE gold.revenue_by_category;
INSERT INTO gold.revenue_by_category (category, orders, quantity, revenue)
SELECT category, count(*), sum(quantity), sum(amount)
FROM clean.clean_orders
GROUP BY category"""


def connect():
    return psycopg.connect(PG_DSN)


def csv_header():
    with open(ORDERS) as f:
        return f.readline().strip().split(",")


def count(cur, table):
    return cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def load_raw():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE raw.raw_orders")
        with open(ORDERS, "rb") as f, cur.copy(f"COPY raw.raw_orders ({CSV_COLUMNS}) FROM STDIN WITH (FORMAT csv, HEADER true)") as copy:
            copy.write(f.read())
        return count(cur, "raw.raw_orders")


def run_sql(sql, table):
    with connect() as conn, conn.cursor() as cur:
        for statement in sql.split(";\n"):
            cur.execute(statement)
        return count(cur, table)


def build_clean():
    return run_sql(BUILD_CLEAN_SQL, "clean.clean_orders")


def build_revenue():
    return run_sql(BUILD_REVENUE_SQL, "gold.revenue_by_category")


def revenue():
    with connect() as conn, conn.cursor() as cur:
        rows = cur.execute("SELECT category, orders, quantity, revenue FROM gold.revenue_by_category ORDER BY revenue DESC").fetchall()
    return [{"category": c, "orders": o, "quantity": q, "revenue": float(r)} for c, o, q, r in rows]
