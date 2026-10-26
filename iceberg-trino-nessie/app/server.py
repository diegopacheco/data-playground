import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import lake
import nessie

INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(url.query)
        ref = params.get("ref", ["main"])[0]
        routes = {
            "/api/summary": lambda: lake.summary(),
            "/api/refs": lambda: nessie.refs(),
            "/api/revenue": lambda: lake.revenue(ref),
            "/api/log": lambda: nessie.log(ref),
        }
        try:
            if url.path in ("/", "/index.html"):
                with open(INDEX, "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            elif url.path in routes:
                self.send_json(200, routes[url.path]())
            else:
                self.send_json(404, {"error": "not found"})
        except ValueError as e:
            self.send_json(400, {"error": str(e)})
        except Exception as e:
            self.send_json(500, {"error": str(e)})


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "20404"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
