import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parent
RESULTS = Path(os.environ.get("RESULTS", "/app/results/results.json"))
SPARK_UI = os.environ.get("SPARK_UI_URL", "http://localhost:26703")


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
        elif self.path == "/api/results":
            if not RESULTS.exists():
                self.send_json(404, {"error": "no results yet, run scripts/bench.sh"})
                return
            report = json.loads(RESULTS.read_text())
            report["spark_ui"] = SPARK_UI
            self.send_json(200, report)
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
