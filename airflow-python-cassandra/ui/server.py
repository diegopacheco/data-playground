import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from cassandra.cluster import Cluster

HOST = os.environ.get("CASSANDRA_HOST", "localhost")
PORT = int(os.environ.get("CASSANDRA_PORT", "9042"))
UI_PORT = int(os.environ.get("UI_PORT", "8000"))
INDEX = (Path(__file__).parent / "index.html").read_bytes()
QUERY = "SELECT category, total_orders, total_quantity, total_revenue FROM sales.revenue_by_category"

session = None


def fetch_revenue():
    global session
    if session is None:
        session = Cluster([HOST], port=PORT).connect()
    rows = [
        {"category": r.category, "total_orders": r.total_orders, "total_quantity": r.total_quantity, "total_revenue": r.total_revenue}
        for r in session.execute(QUERY)
    ]
    return sorted(rows, key=lambda r: r["total_revenue"], reverse=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.reply(200, "text/html; charset=utf-8", INDEX)
        elif self.path == "/api/revenue":
            try:
                self.reply(200, "application/json", json.dumps(fetch_revenue()).encode())
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


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", UI_PORT), Handler).serve_forever()
