import json
import os
import statistics
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import rawcols
from checksums import table_checksums
from formats import FORMATS, run_step

LAKE = os.environ.get("LAKE", "/lake")
RESULTS = os.environ.get("RESULTS", "/bench/results/results.json")
PORT = int(os.environ.get("UI_PORT", "8080"))
HERE = os.path.dirname(os.path.abspath(__file__))
TABLES = ("wide", "normal")
LIVE_RUNS = 3


class BadRequest(Exception):
    pass


def table_dir(query):
    name = query.get("table", ["wide"])[0]
    if name not in TABLES:
        raise BadRequest(f"table must be one of {', '.join(TABLES)}")
    path = os.path.join(LAKE, name)
    if not os.path.isdir(path):
        raise BadRequest(f"table {name} is not in the lake, run the benchmark first")
    return name, path


def spread(names, count):
    step = len(names) / count
    return [names[int(i * step)] for i in range(count)]


def live_project(query):
    name, path = table_dir(query)
    try:
        count = int(query.get("count", ["5"])[0])
    except ValueError:
        raise BadRequest("count must be an integer")
    _, columns = rawcols.read_schema(os.path.join(path, "source"))
    names = [c for c, _ in columns]
    if count < 1 or count > min(500, len(names)):
        raise BadRequest(f"count must be between 1 and {min(500, len(names))}")
    selected = spread(names, count)
    expected = table_checksums(rawcols.read_dir(os.path.join(path, "source"), set(selected)), selected)
    results = []
    for fmt in FORMATS:
        out = run_step(fmt, "project", path, LIVE_RUNS, selected)
        results.append({"name": fmt, "ms": round(statistics.median(out["scan_ms"]), 3), "rows": out["rows"],
                        "matches_source": out["checksums"] == expected})
    return {"table": name, "count": count, "columns": selected, "of_columns": len(names), "results": results}


def live_meta(query):
    name, path = table_dir(query)
    results = []
    for fmt in FORMATS:
        out = run_step(fmt, "meta", path, LIVE_RUNS)
        results.append({"name": fmt, "ms": round(statistics.median(out["meta_ms"]), 3),
                        "columns": out["columns"], "footer_bytes": out["footer_bytes"],
                        "metadata_bytes": out.get("metadata_bytes", out["footer_bytes"])})
    return {"table": name, "results": results}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        try:
            if url.path == "/":
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            elif url.path == "/api/health":
                self.send(200, {"status": "UP"})
            elif url.path == "/api/results":
                if not os.path.exists(RESULTS):
                    self.send(404, {"error": "no results yet, run the benchmark"})
                else:
                    with open(RESULTS, "rb") as f:
                        self.send(200, f.read())
            elif url.path == "/api/project":
                self.send(200, live_project(query))
            elif url.path == "/api/meta":
                self.send(200, live_meta(query))
            else:
                self.send(404, {"error": "not found"})
        except BadRequest as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": str(e)})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"ui on port {PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
