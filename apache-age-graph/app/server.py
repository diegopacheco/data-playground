import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import graph

APP = Path(__file__).resolve().parent


def number(params, name, low, high):
    raw = params.get(name, [None])[0]
    if raw is None or not raw.lstrip("-").isdigit() or not low <= int(raw) <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return int(raw)


ROUTES = {
    "/api/stats": lambda p: graph.stats(),
    "/api/graph": lambda p: graph.graph(),
    "/api/khop": lambda p: graph.khop(number(p, "customer", 1, 10**6), number(p, "k", 1, 4)),
    "/api/path": lambda p: graph.shortest_path(number(p, "from", 1, 10**6), number(p, "to", 1, 10**6)),
    "/api/recommend": lambda p: graph.recommend(number(p, "product", 1, 10**6)),
    "/api/network": lambda p: graph.network(number(p, "customer", 1, 10**6), number(p, "k", 1, 4)),
}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload).encode(), "application/json")

    def run(self, action):
        try:
            self.send_json(200, action())
        except ValueError as e:
            self.send_json(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": str(e).strip()})

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path in ROUTES:
            params = parse_qs(url.query)
            self.run(lambda: ROUTES[url.path](params))
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path == "/api/reload":
            self.run(graph.load)
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    graph.wait_ready()
    print(f"loaded {json.dumps(graph.load())}", flush=True)
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
