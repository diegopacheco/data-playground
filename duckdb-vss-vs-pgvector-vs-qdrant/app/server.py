import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from config import PORTS, RUN

APP = os.path.dirname(os.path.abspath(__file__))


def results():
    with open(os.path.join(RUN, "results.json")) as f:
        return json.load(f)


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/results":
                self.send(200, json.dumps(results()).encode(), "application/json")
            elif path == "/":
                with open(os.path.join(APP, "index.html"), "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            else:
                self.send(404, b'{"error":"not found"}', "application/json")
        except FileNotFoundError:
            self.send(404, b'{"error":"not found"}', "application/json")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def log_message(self, *args):
        return


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORTS["ui"]), Handler).serve_forever()
