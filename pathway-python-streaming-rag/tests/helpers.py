import csv
import glob
import json
import os
import subprocess
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ORDERS = os.path.join(DATA, "orders")
REGIONS = os.path.join(DATA, "regions")
DOCS = os.path.join(DATA, "docs")
WINDOW = 60


def ports():
    with open(os.path.join(ROOT, "scripts", "ports.env")) as env:
        return dict(line.strip().split("=", 1) for line in env if "=" in line)


UI = f"http://localhost:{ports()['ui']}"


def get(name):
    with urllib.request.urlopen(f"{UI}/api/{name}", timeout=10) as response:
        return json.load(response)


def search(query, k=3):
    body = json.dumps({"query": query, "k": k}).encode()
    request = urllib.request.Request(f"{UI}/api/search", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def write_atomic(path, text):
    if os.path.exists(path):
        last = int(os.stat(path).st_mtime)
        while int(time.time()) <= last:
            time.sleep(0.05)
    temp = path + ".tmp"
    with open(temp, "w") as handle:
        handle.write(text)
    os.replace(temp, path)


def wait_for(probe, accept, seconds=30):
    deadline = time.time() + seconds
    value = probe()
    while not accept(value) and time.time() < deadline:
        time.sleep(0.5)
        value = probe()
    return value


def read_csv(folder):
    rows = []
    for path in sorted(glob.glob(os.path.join(folder, "*.csv"))):
        with open(path, newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def kafka(*args, stdin=None):
    result = subprocess.run(["podman", "exec", "-i", "t4-redpanda", "rpk", "topic", *args], input=stdin, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"rpk topic {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def kafka_produce(orders):
    kafka("produce", "orders", stdin="".join(json.dumps(order) + "\n" for order in orders))


def kafka_orders():
    out = kafka("consume", "orders", "--offset", ":end", "--format", "%v\n")
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def all_orders():
    file_rows = [{"order_id": r["order_id"], "region": r["region"], "amount": int(r["amount"]), "ts": int(r["ts"])} for r in read_csv(ORDERS)]
    return file_rows + kafka_orders()


def regions():
    return {r["region"]: {"name": r["name"], "tax_pct": int(r["tax_pct"])} for r in read_csv(REGIONS)}


def expected():
    known = regions()
    windows = {}
    totals = {}
    for order in all_orders():
        region = known.get(order["region"])
        if region is None:
            continue
        gross = order["amount"] * (100 + region["tax_pct"]) // 100
        start = order["ts"] // WINDOW * WINDOW
        w = windows.setdefault((order["region"], start), {"region": order["region"], "window_start": start, "orders": 0, "revenue": 0, "gross": 0, "max_amount": 0})
        w["orders"] += 1
        w["revenue"] += order["amount"]
        w["gross"] += gross
        w["max_amount"] = max(w["max_amount"], order["amount"])
        t = totals.setdefault(order["region"], {"region": order["region"], "name": region["name"], "orders": 0, "revenue": 0, "gross": 0})
        t["orders"] += 1
        t["revenue"] += order["amount"]
        t["gross"] += gross
    return windows, totals


def actual():
    windows = {(w["region"], w["window_start"]): w for w in get("windows")["rows"]}
    totals = {t["region"]: t for t in get("totals")["rows"]}
    return windows, totals


def converge(seconds=30):
    want = expected()
    got = wait_for(actual, lambda value: value == want, seconds)
    return want, got
