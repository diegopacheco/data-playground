import csv
import time

import lake
import nessie
import trino

TABLE_DDL = """CREATE TABLE main.shop.orders (
  order_id integer, customer varchar, product varchar, category varchar,
  quantity integer, price decimal(10,2), ts timestamp(6) with time zone)"""


def sql_text(value):
    return "'" + value.replace("'", "''") + "'"


def values(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return ",\n".join("(%s, %s, %s, %s, %s, DECIMAL %s, from_iso8601_timestamp(%s))" % (
        r["order_id"], sql_text(r["customer"]), sql_text(r["product"]), sql_text(r["category"]),
        r["quantity"], sql_text(r["price"]), sql_text(r["ts"])) for r in rows)


def wait_for_trino():
    for _ in range(60):
        try:
            if trino.ready():
                trino.query("SELECT 1")
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("trino not ready")


def show(title, ref):
    print("== %s (%s @ %s)" % (title, ref, nessie.ref(ref)["hash"][:12]))
    for r in lake.revenue(ref):
        print("  %-12s orders=%-4s qty=%-4s revenue=%s" % (r["category"], r["orders"], r["quantity"], r["revenue"]))


def step(message, sql):
    print("-> " + message)
    trino.query(sql)


def main():
    wait_for_trino()
    step("create schema main.shop", "CREATE SCHEMA IF NOT EXISTS main.shop")
    step("create table main.shop.orders", TABLE_DDL)
    step("load data/orders.csv into main", "INSERT INTO main.shop.orders VALUES " + values("data/orders.csv"))
    print("-> tag initial at main")
    nessie.create("initial", "TAG", "main")
    print("-> create branch dev from main")
    nessie.create("dev", "BRANCH", "main")
    step("dev: raise electronics prices by 10%",
         "UPDATE dev.shop.orders SET price = CAST(price * DECIMAL '1.10' AS decimal(10,2)) WHERE category = 'electronics'")
    step("dev: delete category toys", "DELETE FROM dev.shop.orders WHERE category = 'toys'")
    step("dev: insert data/dev_inserts.csv", "INSERT INTO dev.shop.orders VALUES " + values("data/dev_inserts.csv"))
    show("main before merge", "main")
    show("dev before merge", "dev")
    if lake.revenue("main") != lake.revenue("initial"):
        raise RuntimeError("main changed while working on dev")
    print("-> main unchanged while dev diverged")
    print("-> merge dev into main via Nessie API")
    nessie.merge("dev", "main", "merge dev into main")
    print("-> tag merged at main")
    nessie.create("merged", "TAG", "main")
    show("main after merge", "main")
    print("pipeline done")


if __name__ == "__main__":
    main()
