import os
import duckdb
from cassandra_store import connect

KEYSPACE_DDL = "CREATE KEYSPACE IF NOT EXISTS sales WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}"
TABLE_DDL = "CREATE TABLE IF NOT EXISTS sales.revenue_by_category (category text PRIMARY KEY, total_orders bigint, total_quantity bigint, total_revenue double)"
UPSERT = "INSERT INTO sales.revenue_by_category (category, total_orders, total_quantity, total_revenue) VALUES (?, ?, ?, ?)"


def read_dbt_output(path):
    with duckdb.connect(path, read_only=True) as con:
        return con.sql("select category, total_orders, total_quantity, total_revenue from revenue_by_category").fetchall()


def load(rows):
    cluster, session = connect()
    session.execute(KEYSPACE_DDL)
    session.execute(TABLE_DDL)
    insert = session.prepare(UPSERT)
    for category, orders, quantity, revenue in rows:
        session.execute(insert, (category, int(orders), int(quantity), float(revenue)))
    cluster.shutdown()


def main():
    rows = read_dbt_output(os.environ.get("DUCKDB_PATH", "dbt/sales.duckdb"))
    load(rows)
    print(f"loaded {len(rows)} rows into sales.revenue_by_category")


if __name__ == "__main__":
    main()
