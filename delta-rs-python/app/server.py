import json
import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from lake import versions, open_table, revenue_by_category

INDEX = os.path.join(os.path.dirname(__file__), "index.html")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/":
                with open(INDEX, "rb") as f:
                    self.send(200, "text/html; charset=utf-8", f.read())
            elif url.path == "/api/versions":
                self.json(versions())
            elif url.path == "/api/revenue":
                version = parse_qs(url.query).get("version", [None])[0]
                table = open_table(int(version) if version is not None else None)
                self.json({"version": table.version(), "categories": revenue_by_category(table)})
            else:
                self.json({"error": "not found"}, 404)
        except Exception as e:
            self.json({"error": str(e)}, 500)

    def json(self, body, status=200):
        self.send(status, "application/json", json.dumps(body, default=str).encode())

    def send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "20502"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
