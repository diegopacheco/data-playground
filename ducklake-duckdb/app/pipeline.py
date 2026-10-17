import os
import subprocess
import sys
from lake import connect, commit, rows, ORDERS_CSV
from client import count

APP = os.path.dirname(os.path.abspath(__file__))


def main():
    con = connect()
    commit(con, "create table orders", """
        CREATE TABLE lake.orders (order_id INTEGER, customer VARCHAR, product VARCHAR, category VARCHAR,
        quantity INTEGER, price DECIMAL(10,2), ts TIMESTAMP)
    """)
    commit(con, "client A loads first 150 orders", f"INSERT INTO lake.orders SELECT * FROM {ORDERS_CSV} LIMIT 150")
    print(f"client A pid={os.getpid()} rows={count(con)}", flush=True)

    subprocess.run([sys.executable, os.path.join(APP, "client.py")], check=True)

    print(f"client A pid={os.getpid()} sees rows={count(con)} after client B committed")
    commit(con, "update electronics price +5.00", "UPDATE lake.orders SET price = price + 5.00 WHERE category = 'electronics'")
    commit(con, "delete orders with quantity 5", "DELETE FROM lake.orders WHERE quantity = 5")
    commit(con, "add column channel", "ALTER TABLE lake.orders ADD COLUMN channel VARCHAR DEFAULT 'web'")
    commit(con, "set channel store for toys", "UPDATE lake.orders SET channel = 'store' WHERE category = 'toys'")

    for s in rows(con, "SELECT snapshot_id, commit_message, changes FROM lake.snapshots() ORDER BY snapshot_id"):
        print(s["snapshot_id"], s["commit_message"], s["changes"])


if __name__ == "__main__":
    main()
