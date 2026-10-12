import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTES = {
    "/": (ROOT / "ui" / "index.html", "text/html; charset=utf-8"),
    "/api/results": (ROOT / "results.json", "application/json"),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        route = ROUTES.get(self.path.split("?")[0])
        if route is None or not route[0].exists():
            self.send_error(404)
            return
        body = route[0].read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", route[1])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ.get("PORT", "22900"))), Handler).serve_forever()
