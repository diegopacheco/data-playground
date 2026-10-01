import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE_DB = os.environ.get("STORE_DB", str(HERE.parent / "state" / "store.db"))
PORT = int(os.environ.get("UI_PORT", "22880"))

QUERIES = {
    "/api/totals": "SELECT category, orders, quantity, revenue_cents, last_order_id, updated_at FROM totals ORDER BY revenue_cents DESC",
    "/api/windows": "SELECT category, window_start, orders, quantity, revenue_cents, updated_at FROM windows ORDER BY window_start, category",
    "/api/runs": "SELECT run_id, started_at, events FROM runs ORDER BY run_id",
}


def query(sql):
    if not Path(STORE_DB).exists():
        return []
    conn = sqlite3.connect(f"file:{STORE_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(sql)]
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    for r in rows:
        if "revenue_cents" in r:
            r["revenue"] = r["revenue_cents"] / 100
    return rows


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in QUERIES:
            self.send(200, "application/json", json.dumps(query(QUERIES[path])).encode())
        elif path in ("/", "/index.html"):
            self.send(200, "text/html; charset=utf-8", (HERE / "index.html").read_bytes())
        else:
            self.send(404, "text/plain", b"not found")

    def send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
