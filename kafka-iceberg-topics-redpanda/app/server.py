import json
import os
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from config import ADMIN, LAG_FILE, REST, TOPICS, UI_PORT, orders
from lake import connect, http, rows

APP = os.path.dirname(os.path.abspath(__file__))


def categories(cur, topic):
    return rows(cur, f"""
        SELECT category, count(*) AS orders, sum(quantity) AS quantity, sum(quantity * price) AS revenue
        FROM ({TOPICS[topic]['orders']}) GROUP BY category ORDER BY category
    """)


def snapshots(cur, topic, metadata):
    result = []
    for s in sorted(metadata.get("snapshots", []), key=lambda s: s["sequence-number"]):
        newest = cur.execute(f"SELECT epoch_ms(max(redpanda.timestamp)) FROM lake.redpanda.{topic} AT (VERSION => {s['snapshot-id']})").fetchone()[0]
        summary = s["summary"]
        result.append({
            "snapshot_id": str(s["snapshot-id"]),
            "operation": summary["operation"],
            "committed_at_ms": s["timestamp-ms"],
            "added_records": int(summary.get("added-records", 0)),
            "total_records": int(summary.get("total-records", 0)),
            "added_data_files": int(summary.get("added-data-files", 0)),
            "total_files_size": int(summary.get("total-files-size", 0)),
            "newest_record_ms": newest,
            "commit_lag_s": round((s["timestamp-ms"] - newest) / 1000, 2),
        })
    return result


def table(cur, topic):
    name = f"lake.redpanda.{topic}"
    metadata = http(f"{REST}/v1/namespaces/redpanda/tables/{topic}")["metadata"]
    offsets = rows(cur, f"SELECT count(*) AS rows, count(DISTINCT redpanda.offset) AS distinct_offsets, min(redpanda.offset) AS first_offset, max(redpanda.offset) AS last_offset FROM {name}")[0]
    return {
        "topic": topic,
        "mode": TOPICS[topic]["mode"],
        "table": f"redpanda.{topic}",
        "location": metadata["location"],
        "partition_spec": [f"{f['transform']}: {f['name']}" for f in metadata["partition-specs"][-1]["fields"]],
        "orders_sql": TOPICS[topic]["orders"],
        "columns": rows(cur, f"SELECT column_name, column_type FROM (DESCRIBE {name})"),
        "sample": rows(cur, f"{TOPICS[topic]['sample']} ORDER BY redpanda.offset LIMIT 4"),
        "categories": categories(cur, topic),
        "snapshots": snapshots(cur, topic, metadata),
        **offsets,
    }


def produced():
    result = {}
    for o in orders():
        c = result.setdefault(o["category"], {"category": o["category"], "orders": 0, "quantity": 0, "revenue": Decimal(0)})
        c["orders"] += 1
        c["quantity"] += o["quantity"]
        c["revenue"] += o["quantity"] * Decimal(str(o["price"]))
    return sorted(result.values(), key=lambda c: c["category"])


def batches():
    with open(LAG_FILE) as f:
        return json.load(f)


def license():
    return {**http(f"{ADMIN}/v1/features/license")["license"], **http(f"{ADMIN}/v1/features/enterprise")}


def settings():
    config = http(f"{ADMIN}/v1/cluster_config")
    return {k: config[k] for k in ("iceberg_enabled", "iceberg_catalog_type", "iceberg_target_lag_ms", "iceberg_catalog_commit_interval_ms", "cloud_storage_bucket")}


def encode(value):
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        cur = connect()
        routes = {
            "/api/tables": lambda: [table(cur, t) for t in TOPICS],
            "/api/produced": produced,
            "/api/batches": batches,
            "/api/license": license,
            "/api/settings": settings,
        }
        try:
            if path in routes:
                self.send(200, json.dumps(routes[path](), default=encode).encode(), "application/json")
            elif path == "/":
                with open(os.path.join(APP, "index.html"), "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            else:
                self.send(404, b'{"error":"not found"}', "application/json")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}).encode(), "application/json")
        finally:
            cur.close()


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", UI_PORT), Handler).serve_forever()
