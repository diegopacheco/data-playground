import os

BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA = f"connector = 'kafka', properties.bootstrap.server = '{BOOTSTRAP}'"

OBJECTS = [
    ("customers", "table", """CREATE TABLE customers (
  customer_id INT PRIMARY KEY,
  name VARCHAR,
  region VARCHAR
)"""),
    ("orders", "table", f"""CREATE TABLE orders (
  order_id INT PRIMARY KEY,
  customer_id INT,
  product VARCHAR,
  amount_cents BIGINT,
  event_time TIMESTAMP,
  version INT
) WITH ({KAFKA}, topic = 'orders', scan.startup.mode = 'earliest')
FORMAT PLAIN ENCODE JSON"""),
    ("payments", "source", f"""CREATE SOURCE payments (
  payment_id INT,
  order_id INT,
  paid_cents BIGINT,
  paid_at TIMESTAMP
) WITH ({KAFKA}, topic = 'payments', scan.startup.mode = 'earliest')
FORMAT PLAIN ENCODE JSON"""),
    ("mv_revenue_per_minute", "materialized view", """CREATE MATERIALIZED VIEW mv_revenue_per_minute AS
SELECT window_start, count(*) AS orders, sum(amount_cents)::BIGINT AS revenue_cents
FROM TUMBLE(orders, event_time, INTERVAL '1 MINUTE')
GROUP BY window_start"""),
    ("mv_orders_enriched", "materialized view", """CREATE MATERIALIZED VIEW mv_orders_enriched AS
SELECT o.order_id, o.customer_id, c.name, c.region, o.product, o.amount_cents, o.event_time
FROM orders o JOIN customers c ON o.customer_id = c.customer_id"""),
    ("mv_region_revenue", "materialized view", """CREATE MATERIALIZED VIEW mv_region_revenue AS
SELECT region, count(*) AS orders, sum(amount_cents)::BIGINT AS revenue_cents
FROM mv_orders_enriched
GROUP BY region"""),
    ("mv_region_minute", "materialized view", """CREATE MATERIALIZED VIEW mv_region_minute AS
SELECT region, window_start, count(*) AS orders, sum(amount_cents)::BIGINT AS revenue_cents
FROM TUMBLE(mv_orders_enriched, event_time, INTERVAL '1 MINUTE')
GROUP BY region, window_start"""),
    ("mv_order_payments", "materialized view", """CREATE MATERIALIZED VIEW mv_order_payments AS
SELECT o.order_id, o.amount_cents, count(*) AS payments, sum(p.paid_cents)::BIGINT AS paid_cents,
       o.amount_cents - sum(p.paid_cents)::BIGINT AS due_cents
FROM orders o JOIN payments p ON o.order_id = p.order_id
GROUP BY o.order_id, o.amount_cents"""),
    ("mv_payment_count", "materialized view", """CREATE MATERIALIZED VIEW mv_payment_count AS
SELECT count(*) AS payments FROM payments"""),
    ("region_revenue_sink", "sink", f"""CREATE SINK region_revenue_sink FROM mv_region_revenue
WITH ({KAFKA}, topic = 'region_revenue', primary_key = 'region')
FORMAT UPSERT ENCODE JSON"""),
]

VIEWS = {
    "mv_revenue_per_minute": "SELECT window_start, orders, revenue_cents FROM mv_revenue_per_minute ORDER BY window_start",
    "mv_orders_enriched": "SELECT order_id, customer_id, name, region, product, amount_cents, event_time FROM mv_orders_enriched ORDER BY order_id",
    "mv_region_revenue": "SELECT region, orders, revenue_cents FROM mv_region_revenue ORDER BY region",
    "mv_region_minute": "SELECT region, window_start, orders, revenue_cents FROM mv_region_minute ORDER BY region, window_start",
    "mv_order_payments": "SELECT order_id, amount_cents, payments, paid_cents, due_cents FROM mv_order_payments ORDER BY order_id",
}

KEYS = {
    "mv_revenue_per_minute": ["window_start"],
    "mv_orders_enriched": ["order_id"],
    "mv_region_revenue": ["region"],
    "mv_region_minute": ["region", "window_start"],
    "mv_order_payments": ["order_id"],
}


def drop_statements():
    kinds = {"table": "TABLE", "source": "SOURCE", "materialized view": "MATERIALIZED VIEW", "sink": "SINK"}
    return [f"DROP {kinds[kind]} IF EXISTS {name}" for name, kind, _ in reversed(OBJECTS)]
