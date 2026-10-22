import json
import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from lake import pyiceberg_snapshots, duckdb_snapshots, pyiceberg_aggregates, duckdb_aggregates, duckdb_query

INDEX = os.path.join(os.path.dirname(__file__), "index.html")


def snapshots():
    seen_by_duckdb = {s["snapshot_id"]: s for s in duckdb_snapshots()}
    result = []
    for s in pyiceberg_snapshots():
        d = seen_by_duckdb.get(s["snapshot_id"])
        result.append({**s, "duckdb_sequence_number": d["sequence_number"] if d else None, "duckdb_timestamp": d["timestamp"] if d else None})
    return result


def aggregates(snapshot_id):
    duck = duckdb_aggregates(snapshot_id)
    ice = pyiceberg_aggregates(snapshot_id)
    return {"snapshot_id": str(snapshot_id) if snapshot_id else None, "sql": duckdb_query(snapshot_id), "duckdb": duck, "pyiceberg": ice, "match": duck == ice}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/":
                with open(INDEX, "rb") as f:
                    self.send(200, "text/html; charset=utf-8", f.read())
            elif url.path == "/api/snapshots":
                self.json(snapshots())
            elif url.path == "/api/aggregates":
                snapshot = parse_qs(url.query).get("snapshot", [None])[0]
                self.json(aggregates(int(snapshot) if snapshot else None))
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

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "20603"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
