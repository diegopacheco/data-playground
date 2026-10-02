import csv
import hashlib
import os
from decimal import Decimal, ROUND_HALF_UP

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
REGIONS = ["North America", "Europe", "LATAM", "APAC"]
TIERS = ["gold", "silver", "bronze"]
SUPPLIERS = ["Acme Supply", "Globex Trading", "Initech Goods", "Umbrella Wholesale"]


def pick(key, options):
    return options[int(hashlib.md5(key.encode()).hexdigest(), 16) % len(options)]


def cost_ratio(product):
    return Decimal(55 + int(hashlib.sha1(product.encode()).hexdigest(), 16) % 21) / Decimal(100)


def read_orders():
    with open(os.path.join(DATA, "orders.csv"), newline="") as f:
        return list(csv.DictReader(f))


def customers(orders):
    names = sorted({o["customer"] for o in orders})
    return [
        {"customer_id": i + 1, "customer_name": n, "region": pick("region:" + n, REGIONS), "tier": pick("tier:" + n, TIERS)}
        for i, n in enumerate(names)
    ]


def products(orders):
    unit = {}
    for o in orders:
        price = Decimal(o["price"])
        key = (o["product"], o["category"])
        unit[key] = min(unit.get(key, price), price)
    rows = []
    for i, (product, category) in enumerate(sorted(unit)):
        cost = (unit[(product, category)] * cost_ratio(product)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        rows.append({"product_id": i + 1, "product": product, "category": category, "supplier": pick("supplier:" + product, SUPPLIERS), "cost": str(cost)})
    return rows


def write(name, rows):
    with open(os.path.join(DATA, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main():
    orders = read_orders()
    write("customers.csv", customers(orders))
    write("products.csv", products(orders))
    print("customers.csv and products.csv written")


if __name__ == "__main__":
    main()
