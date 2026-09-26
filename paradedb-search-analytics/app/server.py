import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import queries

INDEX = Path(__file__).resolve().parent / "index.html"


def param(params, name, default=""):
    return params.get(name, [default])[0].strip()


def search(params):
    q = param(params, "q")
    if not q:
        raise ValueError("q is required")
    k = max(1, min(int(param(params, "k", "10")), 35))
    with queries.connect() as conn:
        return queries.search(conn, q, param(params, "mode", "any"), k)


def analytics(params):
    with queries.connect() as conn:
        return queries.analytics(conn, param(params, "q"), param(params, "mode", "any"))


ROUTES = {"/api/search": search, "/api/analytics": analytics}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/":
                self.send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            elif url.path in ROUTES:
                self.send(200, ROUTES[url.path](parse_qs(url.query)))
            else:
                self.send(404, {"error": "not found"})
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": str(e)})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "26401"))
    print(f"listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
