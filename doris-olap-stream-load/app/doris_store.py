import os
from decimal import Decimal
import pymysql

QUERIES = {
    "revenue": """
        SELECT category, count(order_id) AS total_orders, sum(quantity) AS total_quantity,
               sum(quantity * price) AS total_revenue
        FROM orders GROUP BY category ORDER BY total_revenue DESC""",
    "top_products": """
        SELECT product, category, sum(quantity) AS total_quantity, sum(quantity * price) AS total_revenue
        FROM orders GROUP BY product, category ORDER BY total_revenue DESC, product LIMIT 5""",
    "daily": """
        SELECT CAST(date(ts) AS VARCHAR(10)) AS day, count(order_id) AS total_orders,
               sum(quantity * price) AS total_revenue
        FROM orders GROUP BY date(ts) ORDER BY day""",
    "top_customers": """
        SELECT customer, count(order_id) AS total_orders, sum(quantity * price) AS total_revenue
        FROM orders GROUP BY customer ORDER BY total_revenue DESC, customer LIMIT 5""",
}


def connect():
    return pymysql.connect(
        host=os.environ.get("DORIS_HOST", "127.0.0.1"),
        port=int(os.environ.get("DORIS_PORT", "9030")),
        user="root",
        password="",
        database="sales",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def plain(row):
    return {k: float(v) if isinstance(v, Decimal) else v for k, v in row.items()}


def run(name):
    with connect() as conn, conn.cursor() as cur:
        cur.execute(QUERIES[name])
        return [plain(r) for r in cur.fetchall()]
