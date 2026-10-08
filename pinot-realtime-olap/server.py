import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BROKER = os.environ.get("PINOT_BROKER_URL", "http://localhost:23101")
CONSOLE = os.environ.get("PINOT_CONSOLE_URL", "http://localhost:23100")
PORT = int(os.environ.get("UI_PORT", "23180"))
PAGE = (Path(__file__).parent / "index.html").read_bytes()

QUERIES = {
    "/api/stats": "SELECT count(*) AS orders, sum(quantity) AS quantity, sum(revenue) AS revenue, "
                  "distinctcount(customer) AS customers, min(ts) AS first_ts, max(ts) AS last_ts FROM orders",
    "/api/categories": "SELECT category, count(*) AS orders, sum(quantity) AS quantity, sum(revenue) AS revenue "
                       "FROM orders GROUP BY category ORDER BY revenue DESC LIMIT 100",
    "/api/customers": "SELECT customer, count(*) AS orders, sum(quantity) AS quantity, sum(revenue) AS revenue "
                      "FROM orders GROUP BY customer ORDER BY revenue DESC LIMIT 5",
    "/api/daily": "SELECT DATETRUNC('DAY', ts) AS day, count(*) AS orders, sum(revenue) AS revenue "
                  "FROM orders GROUP BY DATETRUNC('DAY', ts) ORDER BY DATETRUNC('DAY', ts) LIMIT 1000",
}

STATS = ("totalDocs", "numDocsScanned", "numSegmentsQueried", "numSegmentsProcessed", "timeUsedMs")


def pinot(sql):
    request = urllib.request.Request(
        f"{BROKER}/query/sql",
        data=json.dumps({"sql": sql}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        body = json.load(response)
    if body.get("exceptions"):
        raise RuntimeError(body["exceptions"][0].get("message", "pinot query failed"))
    table = body["resultTable"]
    names = table["dataSchema"]["columnNames"]
    rows = [{name: tidy(name, value) for name, value in zip(names, row)} for row in table["rows"]]
    return {"sql": sql, "rows": rows, "stats": {key: body.get(key) for key in STATS}}


def tidy(name, value):
    if name == "revenue":
        return round(value, 2)
    if name in ("orders", "quantity", "customers") or name.endswith("_ts") or name == "day":
        return int(value)
    return value


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.reply(200, "text/html; charset=utf-8", PAGE)
        elif self.path == "/api/config":
            self.json(200, {"console": CONSOLE, "broker": BROKER})
        elif self.path in QUERIES:
            try:
                self.json(200, pinot(QUERIES[self.path]))
            except Exception as error:
                self.json(502, {"error": str(error)})
        else:
            self.reply(404, "text/plain", b"not found")

    def json(self, status, payload):
        self.reply(status, "application/json", json.dumps(payload).encode())

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
