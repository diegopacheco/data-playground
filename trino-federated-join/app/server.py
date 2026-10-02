import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from trino import query

HERE = os.path.dirname(os.path.abspath(__file__))
SQL_FILE = os.path.join(HERE, "..", "sql", "federated.sql")
PORT = int(os.environ.get("UI_PORT", "23506"))
SOURCES = [
    ("postgres", "postgres.public.customers", "customers dimension"),
    ("cassandra", "cassandra.sales.orders", "orders fact"),
    ("iceberg", "iceberg.lake.products", "products dimension"),
]


def federated_sql():
    with open(SQL_FILE) as f:
        return f.read().strip()


def federated():
    sql = federated_sql()
    start = time.time()
    columns, rows = query(sql)
    return {"sql": sql, "columns": columns, "rows": rows, "elapsed_ms": int((time.time() - start) * 1000)}


def explain():
    _, rows = query("EXPLAIN " + federated_sql())
    return {"plan": rows[0][0]}


def sources():
    out = []
    for catalog, table, role in SOURCES:
        _, rows = query(f"SELECT count(*) FROM {table}")
        out.append({"catalog": catalog, "table": table, "role": role, "rows": rows[0][0]})
    return {"sources": out}


ROUTES = {"/api/federated": federated, "/api/explain": explain, "/api/sources": sources}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, kind):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if path not in ROUTES:
            return self.send(404, b'{"error":"not found"}', "application/json")
        try:
            self.send(200, json.dumps(ROUTES[path]()).encode(), "application/json")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"ui on port {PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
