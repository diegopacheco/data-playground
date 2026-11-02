import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import runner

APP = Path(__file__).resolve().parent
STATE = {"result": None}
LOCK = threading.Lock()


def run():
    with LOCK:
        STATE["result"] = runner.run()
        return STATE["result"]


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload).encode(), "application/json")

    def do_GET(self):
        if self.path == "/":
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/result":
            self.send_json(200, STATE["result"] or {})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/run":
            self.send_json(404, {"error": "not found"})
            return
        try:
            self.send_json(200, run())
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
