import json
import os
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import data
import sources

APP = Path(__file__).resolve().parent
LOCK = threading.Lock()


def send_run():
    with LOCK:
        run_id = "run-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:-3]
        rows = data.orders(run_id)
        statuses = [sources.ingest(json.dumps(chunk)) for chunk in data.chunks(rows)]
        statuses.append(sources.ingest(data.malformed(run_id)))
        return {"run_id": run_id, "records": len(rows), "requests": len(statuses), "statuses": statuses}


def belongs(record, run_id):
    value = record["value"]
    return value.get("run_id") == run_id or f'"{run_id}' in (value.get("payload") or "")


def outputs(run_id):
    return {
        "run_id": run_id,
        "clean_topic": [r for r in sources.topic("orders-clean") if belongs(r, run_id)],
        "dead_letter_topic": [r for r in sources.topic("orders-dlq") if belongs(r, run_id)],
        "postgres_orders": sources.orders_table(run_id),
        "priority_file": sources.priority_file(run_id),
    }


def pipelines():
    return {"streams": sources.streams(), "files": sources.pipeline_files(), "customers": sources.customers_table()}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload, default=str).encode(), "application/json")

    def guarded(self, fn, *args):
        try:
            self.send_json(200, fn(*args))
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/":
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/pipelines":
            self.guarded(pipelines)
        elif url.path == "/api/metrics":
            self.guarded(sources.counters)
        elif url.path == "/api/runs":
            self.guarded(sources.runs)
        elif url.path == "/api/outputs" and query.get("run"):
            self.guarded(outputs, query["run"][0])
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if urlparse(self.path).path == "/api/send":
            self.guarded(send_run)
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
