import base64
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
import psycopg

CONNECT = os.environ.get("CONNECT_URL", "http://localhost:31401")
PROXY = os.environ.get("PROXY_URL", "http://localhost:31403")
PG_DSN = os.environ.get("PG_DSN", "postgresql://connect:connect@localhost:31404/orders")
PIPELINES = Path(os.environ.get("PIPELINES_DIR", Path(__file__).resolve().parent.parent / "pipelines"))
OUT = Path(os.environ.get("OUT_DIR", "/srv/out"))
TOPICS = ["orders-clean", "orders-dlq"]
METRIC = re.compile(r'^(input|processor|output)_(received|sent|error|batch_sent)\{(.*)\} ([0-9.e+]+)$')
LABEL = re.compile(r'(\w+)="([^"]*)"')


def http(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def ingest(body):
    return http(f"{CONNECT}/orders/ingest", body.encode(), {"Content-Type": "application/json"})[0]


def streams():
    return json.loads(http(f"{CONNECT}/connect/streams")[1])


def pipeline_files():
    root = PIPELINES.parent
    out = {}
    for folder in ["pipelines", "rules", "resources"]:
        for f in sorted((root / folder).glob("*")):
            if f.suffix in (".yaml", ".blobl"):
                out[f"{folder}/{f.name}"] = f.read_text()
    return out


def metrics():
    rows = []
    for line in http(f"{CONNECT}/connect/metrics")[1].decode().splitlines():
        m = METRIC.match(line)
        if not m:
            continue
        labels = dict(LABEL.findall(m.group(3)))
        rows.append({"kind": m.group(1), "name": m.group(2), "stream": labels.get("stream", ""),
                     "label": labels.get("label", ""), "path": labels.get("path", ""), "value": float(m.group(4))})
    return rows


def counters():
    table = {}
    for r in metrics():
        key = (r["stream"], r["kind"], r["label"])
        row = table.setdefault(key, {"stream": r["stream"], "kind": r["kind"], "label": r["label"], "path": r["path"]})
        row[r["name"]] = int(r["value"])
    return sorted(table.values(), key=lambda r: (r["stream"], r["path"]))


def decode(b64):
    return None if b64 is None else base64.b64decode(b64).decode()


def topic(name):
    records = []
    partition = 0
    while True:
        offset = 0
        while True:
            url = f"{PROXY}/topics/{name}/partitions/{partition}/records?offset={offset}&timeout=200&max_bytes=4000000"
            try:
                batch = json.loads(http(url, headers={"Accept": "application/vnd.kafka.binary.v2+json"})[1])
            except urllib.error.HTTPError as e:
                with e:
                    body = json.loads(e.read() or b"{}")
                if body.get("error_code") == 40402:
                    return records
                if body.get("error_code") == 40002:
                    break
                raise
            if not batch:
                break
            for r in batch:
                records.append({"partition": r["partition"], "offset": r["offset"], "key": decode(r.get("key")),
                                "value": json.loads(decode(r["value"]))})
            offset = batch[-1]["offset"] + 1
        partition += 1


def postgres(sql, args=()):
    with psycopg.connect(PG_DSN, connect_timeout=10) as conn:
        cur = conn.execute(sql, args)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def orders_table(run_id):
    return postgres("SELECT id, run_id, customer_id, customer_name, tier, sku, qty, unit_price_cents, total_cents, "
                    "discount_cents, net_cents, priority, country, email, channel FROM orders WHERE run_id = %s ORDER BY id", (run_id,))


def customers_table():
    return postgres("SELECT id, name, tier, country FROM customers ORDER BY id")


def priority_file(run_id):
    f = OUT / "priority" / f"{run_id}.jsonl"
    if not f.exists():
        return []
    return [json.loads(line) for line in f.read_text().splitlines() if line.strip()]


def runs():
    return postgres("SELECT run_id, count(*) AS orders, min(inserted_at)::text AS first_insert FROM orders GROUP BY run_id ORDER BY min(inserted_at) DESC LIMIT 20")
