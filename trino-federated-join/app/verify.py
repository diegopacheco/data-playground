import csv
import json
import os
import sys
import urllib.request
from decimal import Decimal, ROUND_HALF_UP

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
UI_URL = os.environ.get("UI_URL", "http://localhost:23506")
CENT = Decimal("0.01")


def load(name):
    with open(os.path.join(DATA, name), newline="") as f:
        return list(csv.DictReader(f))


def expected():
    region = {c["customer_name"]: c["region"] for c in load("customers.csv")}
    product = {p["product"]: p for p in load("products.csv")}
    groups = {}
    for o in load("orders.csv"):
        p = product[o["product"]]
        key = (region[o["customer"]], p["category"], p["supplier"])
        g = groups.setdefault(key, [0, 0, Decimal(0), Decimal(0)])
        g[0] += 1
        g[1] += int(o["quantity"])
        g[2] += int(o["quantity"]) * Decimal(o["price"])
        g[3] += int(o["quantity"]) * Decimal(p["cost"])
    out = {}
    for key, (orders, units, revenue, cost) in groups.items():
        margin = revenue - cost
        out[key] = (orders, units, revenue.quantize(CENT, ROUND_HALF_UP), cost.quantize(CENT, ROUND_HALF_UP), margin.quantize(CENT, ROUND_HALF_UP), (100 * margin / revenue).quantize(CENT, ROUND_HALF_UP))
    return out


def actual():
    with urllib.request.urlopen(UI_URL + "/api/federated", timeout=120) as r:
        body = json.loads(r.read())
    return {(row[0], row[1], row[2]): (row[3], row[4], Decimal(str(row[5])), Decimal(str(row[6])), Decimal(str(row[7])), Decimal(str(row[8]))) for row in body["rows"]}


def close(a, b):
    return abs(a - b) <= CENT


def main():
    exp, act = expected(), actual()
    errors = []
    if set(exp) != set(act):
        errors.append(f"group keys differ: missing={sorted(set(exp) - set(act))} extra={sorted(set(act) - set(exp))}")
    for key in sorted(set(exp) & set(act)):
        e, a = exp[key], act[key]
        if e[0] != a[0] or e[1] != a[1] or not all(close(x, y) for x, y in zip(e[2:], a[2:])):
            errors.append(f"{key}: expected {e} got {a}")
    total_rev = sum(v[2] for v in exp.values())
    total_margin = sum(v[4] for v in exp.values())
    print(f"groups expected={len(exp)} trino={len(act)}")
    print(f"orders expected={sum(v[0] for v in exp.values())} trino={sum(v[0] for v in act.values())}")
    print(f"revenue expected={total_rev} trino={sum(v[2] for v in act.values())}")
    print(f"margin expected={total_margin} trino={sum(v[4] for v in act.values())}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        print("FAIL", file=sys.stderr)
        sys.exit(1)
    print("PASS federated result matches independent CSV join")


if __name__ == "__main__":
    main()
