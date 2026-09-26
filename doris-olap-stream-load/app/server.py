import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from doris_store import run

INDEX = Path(__file__).with_name("index.html").read_bytes()
ROUTES = {
    "/api/revenue": "revenue",
    "/api/top-products": "top_products",
    "/api/daily": "daily",
    "/api/top-customers": "top_customers",
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.reply(200, "text/html; charset=utf-8", INDEX)
        elif self.path in ROUTES:
            try:
                self.reply(200, "application/json", json.dumps(run(ROUTES[self.path])).encode())
            except Exception as e:
                self.reply(500, "application/json", json.dumps({"error": str(e)}).encode())
        else:
            self.reply(404, "application/json", b'{"error": "not found"}')

    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"serving on port {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
