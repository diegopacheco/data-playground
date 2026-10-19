import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import pipeline

INDEX = Path(__file__).parent / "index.html"


def ids(q):
    raw = q.get("driver_ids", [",".join(str(d) for d in pipeline.gen.DRIVERS)])[0]
    return [int(x) for x in raw.split(",") if x.strip()]


GET = {
    "/api/state": lambda q: pipeline.state(),
    "/api/training": lambda q: pipeline.training_report(),
    "/api/online": lambda q: pipeline.online(ids(q)),
    "/api/latency": lambda q: pipeline.latency(int(q.get("n", ["200"])[0])),
    "/api/definitions": lambda q: pipeline.definitions(),
    "/api/timeline": lambda q: pipeline.timeline(int(q.get("driver_id", ["1001"])[0])),
}

POST = {
    "/api/bootstrap": lambda b: pipeline.bootstrap(),
    "/api/push": lambda b: pipeline.push(b["driver_id"], b.get("conv_rate", 0.5), b.get("acc_rate", 0.9), b.get("trips_today", 1)),
}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def run(self, fn, arg):
        try:
            self.send(200, fn(arg))
        except Exception as e:
            traceback.print_exc()
            self.send(500, {"error": str(e)})

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            return self.send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        if url.path not in GET:
            return self.send(404, {"error": "not found"})
        self.run(GET[url.path], parse_qs(url.query))

    def do_POST(self):
        url = urlparse(self.path)
        if url.path not in POST:
            return self.send(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        self.run(POST[url.path], body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    pipeline.bootstrap()
    print("bootstrap done, serving", flush=True)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("UI_PORT", "8080"))), Handler).serve_forever()
