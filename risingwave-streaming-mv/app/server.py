import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import pipeline
import scenario

APP = Path(__file__).resolve().parent


def objects():
    return [{"name": name, "kind": kind, "sql": sql} for name, kind, sql in pipeline.OBJECTS]


def snapshots():
    return {"phase": scenario.STATE["phase"], "before": scenario.STATE["before"], "after": scenario.STATE["after"], "keys": pipeline.KEYS}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload).encode(), "application/json")

    def guarded(self, fn):
        try:
            self.send_json(200, fn())
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        routes = {
            "/api/live": scenario.view,
            "/api/pipeline": objects,
            "/api/snapshots": snapshots,
            "/api/sink": scenario.sink,
        }
        path = urlparse(self.path).path
        if path == "/":
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif path in routes:
            self.guarded(routes[path])
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/run-all":
            self.guarded(scenario.run_all)
        elif path == "/api/start-live":
            self.send_json(202 if scenario.live() else 409, {"phase": scenario.STATE["phase"]})
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
