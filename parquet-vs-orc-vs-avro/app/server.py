import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "app" / "index.html"
RESULTS = ROOT / "results" / "results.json"
PORT = int(os.environ.get("UI_PORT", "21100"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send(200, "text/html; charset=utf-8", PAGE.read_bytes())
        elif self.path == "/api/results":
            if RESULTS.exists():
                self.send(200, "application/json", RESULTS.read_bytes())
            else:
                self.send(404, "application/json", b'{"error":"results.json not found"}')
        elif self.path == "/api/health":
            self.send(200, "application/json", b'{"status":"UP"}')
        else:
            self.send(404, "text/plain", b"not found")

    def send(self, code, kind, body):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
