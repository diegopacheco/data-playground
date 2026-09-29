import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import settings
from flight_client import read_orders_csv

INDEX = Path(__file__).resolve().parent / "index.html"
LOCK = threading.Lock()
CLIENT = settings.client()
LAST_BENCH = {}


def orders():
    table = CLIENT.fetch("orders")
    return {"rows": table.num_rows, "tail": table.slice(max(0, table.num_rows - 10)).to_pylist()}


def revenue():
    return CLIENT.fetch("revenue_by_category").to_pylist()


def upload():
    uploaded = CLIENT.upload(read_orders_csv(settings.NEW_ORDERS_CSV))
    return {"uploaded": uploaded, **orders()}


def reset():
    return {"rows": CLIENT.reset()}


def bench(query):
    rounds = min(10, max(1, int(query.get("rounds", ["3"])[0])))
    LAST_BENCH.update(CLIENT.benchmark(rounds))
    return LAST_BENCH


GET_ROUTES = {
    "/api/flights": lambda q: CLIENT.flights(),
    "/api/orders": lambda q: orders(),
    "/api/revenue": lambda q: revenue(),
    "/api/bench": bench,
    "/api/bench/last": lambda q: LAST_BENCH or None,
}

POST_ROUTES = {
    "/api/upload": lambda q: upload(),
    "/api/reset": lambda q: reset(),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            self.reply(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        else:
            self.route(GET_ROUTES, url)

    def do_POST(self):
        self.route(POST_ROUTES, urlparse(self.path))

    def route(self, routes, url):
        action = routes.get(url.path)
        if action is None:
            self.reply(404, b'{"error":"not found"}', "application/json")
            return
        try:
            with LOCK:
                body = json.dumps(action(parse_qs(url.query))).encode()
            self.reply(200, body, "application/json")
        except Exception as e:
            self.reply(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def reply(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"ui http://localhost:{settings.UI_PORT} flight {settings.FLIGHT_URL}")
    ThreadingHTTPServer(("127.0.0.1",settings.UI_PORT), Handler).serve_forever()
