import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import embed
import queries

INDEX = Path(__file__).with_name("index.html").read_bytes()


def api(url):
    params = {k: v[0] for k, v in parse_qs(url.query).items()}
    if url.path == "/api/info":
        return queries.info()
    if url.path == "/api/products":
        return queries.products(params, int(params.get("limit") or 50))
    if url.path == "/api/groupby":
        return queries.groupby()
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            return self.reply(200, "text/html; charset=utf-8", INDEX)
        try:
            body = api(url)
            if body is None:
                return self.reply(404, "application/json", b'{"error": "not found"}')
            self.reply(200, "application/json", json.dumps(body).encode())
        except ValueError as e:
            self.reply(400, "application/json", json.dumps({"error": str(e)}).encode())
        except Exception as e:
            self.reply(500, "application/json", json.dumps({"error": str(e)}).encode())

    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    embed.warm()
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"serving on port {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
