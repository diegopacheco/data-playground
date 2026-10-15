import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
import report
import store

APP = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("UI_PORT", "30203"))


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        routes = {
            "/api/proof": lambda con, data: report.proof(con, data),
            "/api/topics": lambda con, data: report.topics(data),
            "/api/events": lambda con, data: data["events"] + data["dual"],
            "/api/aggregates": lambda con, data: report.aggregates(data),
            "/api/dualwrite": lambda con, data: report.dualwrite(con, data),
            "/api/facts": lambda con, data: data["facts"],
        }
        try:
            if path in routes:
                with store.db() as con:
                    body = routes[path](con, report.load(con))
                self.send(200, json.dumps(body).encode(), "application/json")
            elif path == "/":
                with open(os.path.join(APP, "index.html"), "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            else:
                self.send(404, b'{"error":"not found"}', "application/json")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
