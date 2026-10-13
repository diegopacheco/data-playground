import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import clickhouse as ch
import queries

APP = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ["UI_PORT"])
RESULTS = os.environ["RESULTS"]


def results():
    with open(RESULTS, "rb") as f:
        return f.read()


def live():
    return json.dumps({variant: ch.rows(sql)[0][0] for variant, sql in queries.TOTALS.items()}).encode()


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        routes = {"/api/results": results, "/api/live": live}
        try:
            if path in routes:
                self.send(200, routes[path](), "application/json")
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
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
