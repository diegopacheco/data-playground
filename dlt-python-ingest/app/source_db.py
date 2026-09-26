import csv
import json
import os
from pathlib import Path

import psycopg2
import psycopg2.extras

DSN = os.environ.get("SOURCE_DSN", "postgresql://shop:shop@localhost:26900/shop")
CSV_FILE = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data")) / "orders.csv"
CITIES = ["Lisbon", "Porto", "Madrid", "Berlin", "Paris", "Rome", "Vienna", "Prague"]
TIERS = ["bronze", "silver", "gold"]
CUSTOMERS_SINCE = "2026-01-01T00:00:00+00:00"

SCHEMA = """
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS customers;
CREATE TABLE orders (
  order_id integer PRIMARY KEY,
  customer text NOT NULL,
  product text NOT NULL,
  category text NOT NULL,
  quantity integer NOT NULL,
  price numeric(10,2) NOT NULL,
  ts timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  deleted boolean NOT NULL DEFAULT false
);
CREATE TABLE customers (
  id integer PRIMARY KEY,
  name text NOT NULL UNIQUE,
  email text NOT NULL,
  tier text NOT NULL,
  addresses jsonb NOT NULL,
  tags jsonb NOT NULL,
  loyalty jsonb,
  updated_at timestamptz NOT NULL
);
"""


def connect():
    return psycopg2.connect(DSN)


def query(sql, params=None):
    with connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def csv_orders():
    with CSV_FILE.open() as f:
        return list(csv.DictReader(f))


def customer_rows(orders):
    first_category = {}
    for o in orders:
        first_category.setdefault(o["customer"], o["category"])
    rows = []
    for i, name in enumerate(sorted(first_category), start=1):
        addresses = [{"kind": "home", "city": CITIES[i % len(CITIES)], "zip": f"{1000 + i * 7}"}]
        if i % 2 == 0:
            addresses.append({"kind": "work", "city": CITIES[(i + 3) % len(CITIES)], "zip": f"{2000 + i * 11}"})
        tags = [first_category[name]] + (["newsletter"] if i % 3 == 0 else [])
        email = name.lower().replace(" ", ".") + "@mail.test"
        rows.append((i, name, email, TIERS[i % 3], json.dumps(addresses), json.dumps(tags), CUSTOMERS_SINCE))
    return rows


def reset():
    orders = csv_orders()
    with connect() as conn, conn.cursor() as cur:
        cur.execute(SCHEMA)
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO orders (order_id, customer, product, category, quantity, price, ts, updated_at) VALUES %s",
            [(int(o["order_id"]), o["customer"], o["product"], o["category"], int(o["quantity"]), o["price"], o["ts"], o["ts"]) for o in orders],
        )
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO customers (id, name, email, tier, addresses, tags, updated_at) VALUES %s",
            customer_rows(orders),
        )
    return counts()


def ensure_seeded():
    exists = query("SELECT count(*) AS n FROM information_schema.tables WHERE table_name IN ('orders', 'customers')")[0]["n"]
    return counts() if exists == 2 else reset()


def has_column(table, column):
    return bool(query("SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s", (table, column)))


def counts():
    orders = query("SELECT count(*) FILTER (WHERE NOT deleted) AS live, count(*) FILTER (WHERE deleted) AS deleted FROM orders")[0]
    customers = query("SELECT count(*) AS n, count(loyalty) AS loyalty FROM customers")[0]
    return {
        "orders_live": orders["live"],
        "orders_deleted": orders["deleted"],
        "customers": customers["n"],
        "customers_with_loyalty": customers["loyalty"],
        "orders_has_coupon": has_column("orders", "coupon"),
    }


def customer_json(row):
    doc = {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "tier": row["tier"],
        "addresses": row["addresses"],
        "tags": row["tags"],
        "updated_at": row["updated_at"].isoformat(),
    }
    if row["loyalty"] is not None:
        doc["loyalty"] = row["loyalty"]
    return doc


def customers_page(since, page, page_size):
    total = query("SELECT count(*) AS n FROM customers WHERE updated_at >= %s", (since,))[0]["n"]
    rows = query(
        "SELECT * FROM customers WHERE updated_at >= %s ORDER BY id LIMIT %s OFFSET %s",
        (since, page_size, (page - 1) * page_size),
    )
    return {
        "data": [customer_json(r) for r in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, -(-total // page_size)),
    }


def apply_changes():
    with connect() as conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS coupon text")
        cur.execute(
            "UPDATE orders SET quantity = quantity + 1, coupon = 'SAVE10', updated_at = now() "
            "WHERE order_id IN (SELECT order_id FROM orders WHERE NOT deleted ORDER BY random() LIMIT 3) "
            "RETURNING order_id, quantity, coupon"
        )
        updated = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "UPDATE orders SET deleted = true, updated_at = now() "
            "WHERE order_id IN (SELECT order_id FROM orders WHERE NOT deleted AND order_id <> ALL(%s) ORDER BY random() LIMIT 2) "
            "RETURNING order_id",
            ([u["order_id"] for u in updated],),
        )
        deleted = [r["order_id"] for r in cur.fetchall()]
        cur.execute(
            "INSERT INTO orders (order_id, customer, product, category, quantity, price, ts, updated_at, coupon) "
            "SELECT m.max_id + g, o.customer, o.product, o.category, o.quantity, o.price, now(), now(), 'WELCOME' "
            "FROM (SELECT max(order_id) AS max_id FROM orders) m, generate_series(1, 2) g, "
            "LATERAL (SELECT * FROM orders WHERE NOT deleted ORDER BY random() + g LIMIT 1) o "
            "RETURNING order_id, customer, product, quantity, coupon"
        )
        inserted = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "UPDATE customers SET tier = 'platinum', "
            "loyalty = jsonb_build_object('points', 100 + id * 10, 'level', 'platinum'), "
            "addresses = addresses || jsonb_build_array(jsonb_build_object('kind', 'shipping', 'city', 'Dublin', 'zip', 'D0' || id)), "
            "updated_at = now() "
            "WHERE id IN (SELECT id FROM customers ORDER BY random() LIMIT 2) "
            "RETURNING id, tier, loyalty, jsonb_array_length(addresses) AS addresses"
        )
        customers = [dict(r) for r in cur.fetchall()]
    for o in inserted + updated:
        o["order_id"] = int(o["order_id"])
    return {"updated": updated, "deleted": deleted, "inserted": inserted, "customers": customers, "counts": counts()}
