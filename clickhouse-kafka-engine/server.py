import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CLICKHOUSE = os.environ.get("CLICKHOUSE_URL", "http://localhost:23123")
PORT = int(os.environ.get("UI_PORT", "23080"))
PAGE = (Path(__file__).parent / "index.html").read_bytes()

QUERIES = {
    "/api/totals": """
        SELECT category,
               sum(total_orders) AS orders,
               sum(total_quantity) AS quantity,
               sum(total_revenue) AS revenue
        FROM sales.category_totals
        GROUP BY category
        ORDER BY revenue DESC
    """,
    "/api/stats": """
        SELECT count() AS orders,
               uniqExact(category) AS categories,
               sum(quantity * price) AS revenue,
               toString(max(ts)) AS last_ts
        FROM sales.orders
    """,
}


def clickhouse(sql):
    params = urllib.parse.urlencode({
        "output_format_json_quote_64bit_integers": 0,
        "output_format_json_quote_decimals": 0,
    })
    request = urllib.request.Request(f"{CLICKHOUSE}/?{params}", data=(sql + " FORMAT JSON").encode())
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)["data"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.reply(200, "text/html; charset=utf-8", PAGE)
        elif self.path in QUERIES:
            try:
                body = json.dumps(clickhouse(QUERIES[self.path]))
                self.reply(200, "application/json", body.encode())
            except Exception as error:
                self.reply(502, "application/json", json.dumps({"error": str(error)}).encode())
        else:
            self.reply(404, "text/plain", b"not found")

    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
