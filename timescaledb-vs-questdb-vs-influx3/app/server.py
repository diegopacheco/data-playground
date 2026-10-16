import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import influx
import questdb
import timescale
from dataset import RESULTS
from pipeline import lines

APP = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("S7_UI_PORT", "30603"))
ENGINES = {"timescaledb": timescale, "questdb": questdb, "influx3": influx}
SOURCES = {"raw": "downsample_1h", "rollup": "rollup_1h"}


def hourly(query):
    engine = ENGINES[query.get("engine", ["timescaledb"])[0]]
    return "\n".join(lines(engine, SOURCES[query.get("source", ["raw"])[0]])) + "\n"


def series(query):
    device = query.get("device", ["d000"])[0]
    return {name: sorted(row[1:] for row in engine.hourly(engine.query("rollup_1h")) if row[0] == device)
            for name, engine in ENGINES.items()}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path == "/api/results":
                with open(RESULTS, "rb") as f:
                    self.send(200, f.read(), "application/json")
            elif url.path == "/api/hourly":
                self.send(200, hourly(query).encode(), "text/plain; charset=utf-8")
            elif url.path == "/api/series":
                self.send(200, json.dumps(series(query)).encode(), "application/json")
            elif url.path == "/":
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
