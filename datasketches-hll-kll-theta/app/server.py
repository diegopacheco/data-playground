import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import sketches

APP = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("UI_PORT", "8080"))


def parse_parts(query):
    raw = parse_qs(query).get("partitions", [""])[0]
    parts = sorted({int(x) for x in raw.split(",") if x.strip() != ""}) if raw else list(range(sketches.PARTITIONS))
    if not parts or any(p < 0 or p >= sketches.PARTITIONS for p in parts):
        raise ValueError(f"partitions must be between 0 and {sketches.PARTITIONS - 1}")
    return parts


def exact_for(parts):
    truth, _, _, _ = sketches.exact(sketches.load_many(parts))
    return truth


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path in ("/", "/index.html"):
                with open(os.path.join(APP, "index.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if url.path == "/api/health":
                return self.send(200, {"status": "ok", "results": os.path.exists(os.path.join(sketches.RESULTS, "results.json"))})
            if url.path == "/api/results":
                path = os.path.join(sketches.RESULTS, "results.json")
                if not os.path.exists(path):
                    return self.send(404, {"error": "no results yet, run scripts/sketch.sh"})
                with open(path, "rb") as f:
                    return self.send(200, f.read())
            if url.path == "/api/merge":
                return self.send(200, sketches.merge(parse_parts(url.query)))
            if url.path == "/api/exact":
                return self.send(200, exact_for(parse_parts(url.query)))
            return self.send(404, {"error": "not found"})
        except (ValueError, FileNotFoundError) as e:
            return self.send(400, {"error": str(e)})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"listening on {PORT}")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
