import json
import os
import threading
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import scenarios

APP = Path(__file__).resolve().parent
RESULTS = {}
LOCK = threading.Lock()


def run(name):
    with LOCK:
        result = scenarios.SCENARIOS[name]()
        result["ran_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
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
        path = urlparse(self.path).path
        if path == "/":
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/results":
            self.send_json(200, RESULTS)
        elif path == "/api/pipeline":
            self.guarded(scenarios.pipeline)
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 3 and parts[:2] == ["api", "run"] and parts[2] in scenarios.SCENARIOS:
            self.guarded(run, parts[2])
        elif parts == ["api", "run-all"]:
            self.guarded(lambda: {name: run(name) for name in scenarios.SCENARIOS})
        elif parts == ["api", "deploy"]:
            self.guarded(scenarios.deploy)
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
