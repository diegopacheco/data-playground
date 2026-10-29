import json
import os
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pg8000.native

UI_PORT = int(os.environ.get("UI_PORT", "8000"))
KESTRA_URL = os.environ.get("KESTRA_URL", "http://localhost:24080")
INDEX = (Path(__file__).parent / "index.html").read_bytes()

REVENUE_SQL = "SELECT category, total_orders, total_quantity, total_revenue FROM revenue_by_category ORDER BY total_revenue DESC"
QUALITY_SQL = "SELECT execution_id, upstream_execution_id, checked_at, source_rows, loaded_orders, categories, bad_rows, passed FROM dq_results ORDER BY checked_at DESC LIMIT 10"


def connect():
    return pg8000.native.Connection(
        user=os.environ.get("PG_USER", "sales"),
        password=os.environ.get("PG_PASSWORD", "sales"),
        host=os.environ.get("PG_HOST", "localhost"),
        port=int(os.environ.get("PG_PORT", "5432")),
        database=os.environ.get("PG_DB", "sales"),
    )


def query(sql):
    conn = connect()
    try:
        rows = conn.run(sql)
        names = [c["name"] for c in conn.columns]
        return [dict(zip(names, row)) for row in rows]
    finally:
        conn.close()


def to_json(value):
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        routes = {
            "/api/revenue": lambda: query(REVENUE_SQL),
            "/api/quality": lambda: query(QUALITY_SQL),
            "/api/config": lambda: {"kestra_url": KESTRA_URL},
        }
        if self.path == "/":
            self.reply(200, "text/html; charset=utf-8", INDEX)
        elif self.path in routes:
            try:
                self.reply(200, "application/json", json.dumps(routes[self.path](), default=to_json).encode())
            except Exception as e:
                self.reply(503, "application/json", json.dumps({"error": str(e)}).encode())
        else:
            self.reply(404, "text/plain", b"not found")

    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", UI_PORT), Handler).serve_forever()
