import json
import os
import threading
from datetime import date, datetime
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pipeline
import source_db

INDEX = Path(__file__).with_name("index.html").read_bytes()
LOCK = threading.Lock()


def encode(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def param(params, name, default=""):
    return params.get(name, [default])[0].strip()


def overview():
    return {
        "versions": {
            "dlt": version("dlt"),
            "duckdb": version("duckdb"),
            "postgres": source_db.query("SHOW server_version")[0]["server_version"],
        },
        "pipeline": pipeline.PIPELINE,
        "dataset": pipeline.DATASET,
        "source": source_db.counts(),
        "runs": pipeline.load_runs(),
        "loads": pipeline.loads(),
        "tables": pipeline.tables(),
    }


def read_only(statement):
    if statement.split(None, 1)[0].lower() not in ("select", "with", "describe", "show"):
        raise ValueError("only SELECT, WITH, DESCRIBE and SHOW are allowed")
    return pipeline.sql(statement)


def reset():
    pipeline.reset()
    return {"source": source_db.reset()}


GETS = {
    "/api/overview": lambda p: overview(),
    "/api/schema": lambda p: {"current": pipeline.schema(), "versions": pipeline.versions()},
    "/api/sql": lambda p: read_only(param(p, "q")),
    "/source/customers": lambda p: source_db.customers_page(
        param(p, "updated_since", "1970-01-01T00:00:00+00:00"),
        int(param(p, "page", "1")),
        int(param(p, "page_size", "5")),
    ),
}

POSTS = {
    "/api/run": pipeline.run,
    "/api/changes": source_db.apply_changes,
    "/api/reset": reset,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            return self.reply(200, "text/html; charset=utf-8", INDEX)
        if url.path == "/source/customers":
            return self.call(GETS[url.path], parse_qs(url.query))
        self.handle_api(GETS.get(url.path), parse_qs(url.query))

    def do_POST(self):
        action = POSTS.get(urlparse(self.path).path)
        self.handle_api(action and (lambda p: action()), {})

    def handle_api(self, fn, params):
        if fn is None:
            return self.reply(404, "application/json", b'{"error": "not found"}')
        with LOCK:
            self.call(fn, params)

    def call(self, fn, params):
        try:
            self.reply(200, "application/json", json.dumps(fn(params), default=encode).encode())
        except ValueError as e:
            self.reply(400, "application/json", json.dumps({"error": str(e)}).encode())
        except Exception as e:
            self.reply(500, "application/json", json.dumps({"error": f"{type(e).__name__}: {e}"}).encode())

    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    source_db.ensure_seeded()
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"serving on port {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
