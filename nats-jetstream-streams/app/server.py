import asyncio
import json
import os
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import scenarios

APP = Path(__file__).resolve().parent
RESULTS = {}
LOCK = threading.Lock()


def run(name, fn, *args):
    with LOCK:
        result = asyncio.run(fn(*args))
        result["ran_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if name:
            RESULTS[name] = result
        return result


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload).encode(), "application/json")

    def guarded(self, fn, *args):
        try:
            self.send_json(200, fn(*args))
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/results":
            self.send_json(200, RESULTS)
        elif url.path == "/api/cluster":
            self.guarded(run, None, scenarios.cluster)
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        parts = url.path.strip("/").split("/")
        query = parse_qs(url.query)
        if len(parts) == 3 and parts[:2] == ["api", "run"] and parts[2] in scenarios.SCENARIOS:
            self.guarded(run, parts[2], scenarios.SCENARIOS[parts[2]])
        elif url.path == "/api/run-all":
            self.guarded(lambda: {name: run(name, fn) for name, fn in scenarios.SCENARIOS.items()})
        elif url.path == "/api/ledger":
            self.guarded(run, None, scenarios.ledger, int(query.get("n", ["100"])[0]))
        elif url.path == "/api/stepdown":
            self.guarded(run, None, scenarios.stepdown)
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
