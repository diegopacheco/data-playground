import csv
import datetime
import os
import random

DATA = os.environ.get("DATA_DIR", "/data")
COUNTRIES = ["Brazil", "Canada", "Germany", "India", "Japan", "Mexico", "Spain", "USA"]
TIERS = ["bronze", "silver", "gold"]
PRODUCTS = {"laptop": 1200, "phone": 800, "monitor": 300, "keyboard": 60, "mouse": 25, "headset": 90, "camera": 450, "tablet": 500}
STATUSES = ["placed"] * 6 + ["shipped"] * 3 + ["cancelled"]
CUSTOMERS = 300
BATCHES = {1: range(1, 30001), 2: range(30001, 40001)}


def customers(rng):
    rows = []
    for cid in range(1, CUSTOMERS + 1):
        rows.append([cid, f"customer-{cid:03d}", rng.choice(COUNTRIES), rng.choice(TIERS)])
    return rows


def orders(rng, ids, start):
    rows = []
    for oid in ids:
        product = rng.choice(list(PRODUCTS))
        cents = PRODUCTS[product] * 100 + rng.randint(-1500, 1500)
        day = start + datetime.timedelta(days=rng.randint(0, 29))
        rows.append([oid, rng.randint(1, CUSTOMERS), product, rng.randint(1, 5), f"{cents // 100}.{cents % 100:02d}", rng.choice(STATUSES), day.isoformat()])
    return rows


def write(name, header, rows):
    with open(os.path.join(DATA, name), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {name} with {len(rows)} rows")


if __name__ == "__main__":
    rng = random.Random(2026)
    os.makedirs(DATA, exist_ok=True)
    write("customers.csv", ["customer_id", "name", "country", "tier"], customers(rng))
    header = ["order_id", "customer_id", "product", "quantity", "price", "status", "order_date"]
    write("orders-batch-1.csv", header, orders(rng, BATCHES[1], datetime.date(2026, 7, 1)))
    write("orders-batch-2.csv", header, orders(rng, BATCHES[2], datetime.date(2026, 8, 1)))
