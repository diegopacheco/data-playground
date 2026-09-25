import csv
import os

CASSANDRA_HOST = os.environ.get("CASSANDRA_HOST", "localhost")
CASSANDRA_PORT = int(os.environ.get("CASSANDRA_PORT", "9042"))

KEYSPACE_CQL = "CREATE KEYSPACE IF NOT EXISTS sales WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}"
TABLE_CQL = "CREATE TABLE IF NOT EXISTS sales.revenue_by_category (category text PRIMARY KEY, total_orders bigint, total_quantity bigint, total_revenue double)"
INSERT_CQL = "INSERT INTO sales.revenue_by_category (category, total_orders, total_quantity, total_revenue) VALUES (%s, %s, %s, %s)"


def read_orders(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def aggregate(orders):
    totals = {}
    for o in orders:
        t = totals.setdefault(o["category"], {"category": o["category"], "total_orders": 0, "total_quantity": 0, "total_revenue": 0.0})
        qty = int(o["quantity"])
        t["total_orders"] += 1
        t["total_quantity"] += qty
        t["total_revenue"] += qty * float(o["price"])
    for t in totals.values():
        t["total_revenue"] = round(t["total_revenue"], 2)
    return sorted(totals.values(), key=lambda t: t["category"])


def connect():
    from cassandra.cluster import Cluster
    cluster = Cluster([CASSANDRA_HOST], port=CASSANDRA_PORT)
    return cluster, cluster.connect()


def save(rows):
    cluster, session = connect()
    try:
        session.execute(KEYSPACE_CQL)
        session.execute(TABLE_CQL)
        for r in rows:
            session.execute(INSERT_CQL, (r["category"], r["total_orders"], r["total_quantity"], r["total_revenue"]))
    finally:
        cluster.shutdown()
