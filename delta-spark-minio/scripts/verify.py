import csv
import json
import sys
import urllib.request
from decimal import Decimal

root, api = sys.argv[1], sys.argv[2]
failures = []


def fetch(name):
    with urllib.request.urlopen(f"{api}/{name}") as r:
        return json.load(r)


def load(path):
    with open(path) as f:
        return {int(r["order_id"]): r for r in csv.DictReader(f)}


def revenue(rows):
    out = {}
    for r in rows.values():
        c = out.setdefault(r["category"], [0, Decimal("0")])
        c[0] += 1
        c[1] += int(r["quantity"]) * Decimal(r["price"])
    return out


def check(label, expected, actual):
    ok = expected == actual
    print(f"{'OK  ' if ok else 'FAIL'} {label}: expected={expected} actual={actual}")
    if not ok:
        failures.append(label)


orders = load(f"{root}/data/orders.csv")
updates = load(f"{root}/data/updates.csv")
merged = dict(orders)
merged.update(updates)
changed = [k for k in updates if k in orders and orders[k]["price"] != updates[k]["price"]]
inserted = [k for k in updates if k not in orders]
before, after = revenue(orders), revenue(merged)

for row in fetch("revenue"):
    c = row["category"]
    check(f"{c} before", (before[c][0], before[c][1]), (row["orders_before"], Decimal(str(row["revenue_before"]))))
    check(f"{c} after", (after[c][0], after[c][1]), (row["orders_after"], Decimal(str(row["revenue_after"]))))
check("categories", sorted(after), sorted(r["category"] for r in fetch("revenue")))

versions = {v["version"]: v for v in fetch("versions")}
check("version 0 rows", len(orders), versions[0]["rows"])
check("version 1 rows", len(merged), versions[1]["rows"])
check("version 0 revenue", sum(v[1] for v in before.values()), Decimal(str(versions[0]["revenue"])))
check("version 1 revenue", sum(v[1] for v in after.values()), Decimal(str(versions[1]["revenue"])))

summary = {r["_change_type"]: r["count"] for r in fetch("change_summary")}
check("cdf change types", {"insert": len(inserted), "update_preimage": len(changed), "update_postimage": len(changed)}, summary)

changes = fetch("changes")
pre = {r["order_id"]: Decimal(str(r["price"])) for r in changes if r["_change_type"] == "update_preimage"}
post = {r["order_id"]: Decimal(str(r["price"])) for r in changes if r["_change_type"] == "update_postimage"}
ins = sorted(r["order_id"] for r in changes if r["_change_type"] == "insert")
check("cdf preimage prices", {k: Decimal(orders[k]["price"]) for k in changed}, pre)
check("cdf postimage prices", {k: Decimal(updates[k]["price"]) for k in changed}, post)
check("cdf inserted ids", sorted(inserted), ins)
check("cdf commit version", {1}, {r["_commit_version"] for r in changes})

ops = [h["operation"] for h in fetch("history")]
check("history starts with write and merge", ["WRITE", "MERGE"], ops[:2])
check("history has vacuum", True, "VACUUM END" in ops)

vac = fetch("vacuum")
check("vacuum removed dry run files", set(), set(vac["dry_run"]) & set(vac["files_after"]))
check("vacuum dry run not empty", True, len(vac["dry_run"]) > 0)
check("latest rows after vacuum", len(merged), vac["latest_rows_after_vacuum"])
check("version 0 unreadable after vacuum", True, vac["version0_after_vacuum"].startswith("failed"))

if failures:
    print(f"{len(failures)} checks failed", file=sys.stderr)
    sys.exit(1)
print("all checks passed")
