import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parent
COMPARISON = Path(os.environ.get("COMPARISON_PATH", APP.parent / "comparison.json"))
PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send(200, (APP / "index.html").read_text(), "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self.send(200, json.dumps({"status": "UP"}), "application/json")
        elif self.path == "/api/comparison":
            if COMPARISON.exists():
                self.send(200, COMPARISON.read_text(), "application/json")
            else:
                self.send(404, json.dumps({"error": "comparison.json not found, run scripts/test-all.sh"}), "application/json")
        else:
            self.send(404, json.dumps({"error": "not found"}), "application/json")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
