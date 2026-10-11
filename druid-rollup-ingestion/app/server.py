import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import report

INDEX = Path(__file__).with_name("index.html")
ROUTES = {
    "/api/summary": report.summary,
    "/api/segments": report.segments_per_day,
    "/api/categories": report.categories,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            self.send(200, "text/html; charset=utf-8", INDEX.read_bytes())
        elif path in ROUTES:
            try:
                self.send(200, "application/json", json.dumps(ROUTES[path]()).encode())
            except Exception as error:
                self.send(502, "application/json", json.dumps({"error": str(error)}).encode())
        else:
            self.send(404, "application/json", b'{"error":"not found"}')

    def send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "23201"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
