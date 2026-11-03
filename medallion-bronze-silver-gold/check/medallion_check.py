import csv
import json
import re
import sys
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path

TOP = 10
INT_MAX = 2147483647
TS = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


def reason(r):
    o, cu, ca, q, p, t = (r[k].strip() for k in ("order_id", "customer", "category", "quantity", "price", "ts"))
    if not re.fullmatch(r"[0-9]+", o):
        return "invalid order_id"
    if cu == "":
        return "missing customer"
    if ca == "":
        return "missing category"
    if not re.fullmatch(r"-?[0-9]+", q):
        return "malformed quantity"
    if int(q) <= 0 or int(q) > INT_MAX:
        return "non-positive quantity"
    if not re.fullmatch(r"[0-9]+([.][0-9]{1,2})?", p):
        return "malformed price"
    if Decimal(p) <= 0:
        return "non-positive price"
    if not TS.match(t):
        return "malformed ts"
    try:
        datetime.strptime(t, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return "malformed ts"
    return None


def load(landing):
    rows = []
    for f in sorted(Path(landing).glob("*.csv")):
        with open(f, newline="") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def expected(landing):
    rows = load(landing)
    reasons, latest = {}, {}
    for r in rows:
        why = reason(r)
        if why:
            reasons[why] = reasons.get(why, 0) + 1
            continue
        latest[int(r["order_id"].strip())] = {
            "customer": r["customer"].strip(),
            "category": r["category"].strip().lower(),
            "quantity": int(r["quantity"].strip()),
            "revenue": int(r["quantity"].strip()) * Decimal(r["price"].strip()),
            "day": r["ts"].strip()[:10],
        }
    cat, day, cust = {}, {}, {}
    for o in latest.values():
        for bucket, key in ((cat, o["category"]), (day, o["day"])):
            n, q, rev = bucket.get(key, (0, 0, Decimal(0)))
            bucket[key] = (n + 1, q + o["quantity"], rev + o["revenue"])
        n, rev = cust.get(o["customer"], (0, Decimal(0)))
        cust[o["customer"]] = (n + 1, rev + o["revenue"])
    top = sorted(cust.items(), key=lambda kv: (-kv[1][1], kv[0]))[:TOP]
    return {
        "bronze_rows": len(rows),
        "silver_rows": len(latest),
        "quarantine": [f"{k}|{v}" for k, v in sorted(reasons.items())],
        "revenue_by_category": [f"{k}|{n}|{q}|{rev:.2f}" for k, (n, q, rev) in sorted(cat.items())],
        "daily_revenue": [f"{k}|{n}|{q}|{rev:.2f}" for k, (n, q, rev) in sorted(day.items())],
        "top_customers": [f"{i}|{k}|{n}|{rev:.2f}" for i, (k, (n, rev)) in enumerate(top, 1)],
    }


def get(api, path):
    with urllib.request.urlopen(api + path) as resp:
        return json.load(resp)


def actual(api):
    layers = {l["table_name"]: l["row_count"] for l in get(api, "/layers")}
    gold = lambda t: get(api, f"/gold?table={t}")["rows"]
    money = lambda v: f"{Decimal(str(v)):.2f}"
    return {
        "bronze_rows": layers["bronze.orders_raw"],
        "silver_rows": layers["silver.orders"],
        "quarantine": [f"{r['reason']}|{r['row_count']}" for r in get(api, "/quarantine")["reasons"]],
        "revenue_by_category": [f"{r['category']}|{r['orders']}|{r['quantity']}|{money(r['revenue'])}" for r in gold("revenue_by_category")],
        "daily_revenue": [f"{r['order_date']}|{r['orders']}|{r['quantity']}|{money(r['revenue'])}" for r in gold("daily_revenue")],
        "top_customers": [f"{r['rank']}|{r['customer']}|{r['orders']}|{money(r['revenue'])}" for r in gold("top_customers")],
    }


def show(result):
    for k, v in result.items():
        if isinstance(v, list):
            print(f"[{k}]")
            print("\n".join(v))
        else:
            print(f"{k}={v}")


if __name__ == "__main__":
    mode, source = sys.argv[1], sys.argv[2]
    show(expected(source) if mode == "expected" else actual(source))
