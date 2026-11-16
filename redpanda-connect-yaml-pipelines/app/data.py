import csv
import random
from pathlib import Path

CUSTOMERS_CSV = Path(__file__).resolve().parent.parent / "data" / "customers.csv"
CHUNK = 25


def customers():
    with open(CUSTOMERS_CSV, newline="") as f:
        return list(csv.DictReader(f))


def order(rng, run_id, n, customer):
    email = f"{customer['name'].split()[0]}.{n}@Mail.com"
    return {
        "id": f"{run_id}-{n:04d}",
        "run_id": run_id,
        "customer_id": customer["id"],
        "sku": f"SKU-{rng.randint(1, 20):02d}",
        "qty": rng.randint(1, 10),
        "unit_price_cents": rng.randint(500, 30000),
        "email": rng.choice([email, email.upper(), f"  {email} "]),
        "country": rng.choice([customer["country"], customer["country"].lower()]),
        "channel": rng.choice(["web", "mobile"]),
    }


BREAKERS = [
    lambda o: o.pop("id"),
    lambda o: o.update(id=""),
    lambda o: o.update(customer_id="C-7"),
    lambda o: o.pop("customer_id"),
    lambda o: o.update(qty=0),
    lambda o: o.update(qty=250),
    lambda o: o.update(qty=2.5),
    lambda o: o.update(qty="3"),
    lambda o: o.update(unit_price_cents=0),
    lambda o: o.update(unit_price_cents=-5),
    lambda o: o.update(email="no-at-sign"),
    lambda o: o.pop("email"),
    lambda o: o.update(country="FR"),
    lambda o: o.update(country=""),
]


def orders(run_id, seed=7):
    rng = random.Random(seed)
    people = customers()
    rows = []
    n = 0

    def next_order(customer=None):
        nonlocal n
        n += 1
        return order(rng, run_id, n, customer or rng.choice(people))

    for _ in range(80):
        rows.append(next_order())
    for _ in range(8):
        o = next_order()
        o["channel"] = "loadtest"
        rows.append(o)
    for breaker in BREAKERS:
        o = next_order()
        breaker(o)
        rows.append(o)
    for unknown in ["c050", "c099", "c777"]:
        o = next_order()
        o["customer_id"] = unknown
        rows.append(o)
    o = next_order()
    o.pop("sku")
    o.pop("channel")
    rows.append(o)
    rng.shuffle(rows)
    originals = [r for r in rows if r.get("id") and r.get("channel") != "loadtest"]
    for original in rng.sample(originals, 10):
        dup = dict(original)
        dup["qty"] = (dup["qty"] if isinstance(dup["qty"], int) else 1) % 10 + 1
        rows.append(dup)
    return rows


def chunks(rows):
    return [rows[i:i + CHUNK] for i in range(0, len(rows), CHUNK)]


def malformed(run_id):
    return '[{"id": "' + run_id + '-broken", "run_id": "' + run_id + '", "qty": 1,, oops'
