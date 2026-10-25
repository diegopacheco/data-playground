import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import db
import embed
import lake
import verify

APP = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("UI_PORT", "30704"))


def search(conn, query):
    text = query.get("q", [""])[0].strip()
    if not text:
        return []
    k = min(int(query.get("k", ["5"])[0]), 20)
    return db.rows(conn, db.SEARCH, {"q": embed.to_pg(embed.embed_query(text)), "k": k})


def snapshots(conn):
    mark = str(db.watermark(conn))
    return [{**s, "watermark": s["snapshot_id"] == mark} for s in lake.snapshots(lake.load_table())]


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
        routes = {
            "/api/rounds": lambda conn: db.rounds(conn),
            "/api/snapshots": snapshots,
            "/api/verify": lambda conn: verify.run(conn, lake.load_table()),
            "/api/search": lambda conn: search(conn, query),
        }
        try:
            if url.path in routes:
                with db.connect() as conn:
                    self.send(200, json.dumps(routes[url.path](conn)).encode(), "application/json")
            elif url.path == "/":
                with open(os.path.join(APP, "index.html"), "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            else:
                self.send(404, b'{"error":"not found"}', "application/json")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    embed.model()
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
