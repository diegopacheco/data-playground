import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import kappa_arch
import lambda_arch
import pipeline
import scenario

APP = Path(__file__).resolve().parent


def one(query, name, default=None):
    return query.get(name, [default])[0]


def get_routes(path, q):
    if path == "/api/scenario":
        return (200, scenario.REPORT) if scenario.REPORT else (404, {"error": "no scenario run yet, POST /api/scenario"})
    if path == "/api/state":
        return 200, pipeline.state()
    if path == "/api/views":
        return 200, pipeline.views()
    if path == "/api/lambda/serving":
        return 200, pipeline.table("lambda_serving")
    if path == "/api/kappa/serving":
        return 200, pipeline.table("kappa_serving")
    if path == "/api/kappa/table":
        version = one(q, "version", "")
        kappa_arch.validate(version)
        return 200, pipeline.table(kappa_arch.daily(version))
    if path == "/api/truth":
        return 200, pipeline.truth(one(q, "logic", "v2"))
    return None


def post_routes(path, q):
    day = one(q, "day")
    if path == "/api/scenario":
        return 200, scenario.run()
    if path == "/api/produce":
        return 200, pipeline.produce_live(one(q, "kind", "late"), int(one(q, "count", "20")))
    if path == "/api/rewind":
        pipeline.rewind()
        return 200, pipeline.state()
    if path == "/api/lambda/backfill":
        return 200, pipeline.locked(lambda_arch.batch, [day] if day else None)
    if path == "/api/lambda/nightly":
        return 200, pipeline.locked(lambda_arch.batch, None, True)
    if path == "/api/lambda/deploy":
        return 200, pipeline.locked(lambda_arch.deploy, one(q, "layer", ""), one(q, "logic", ""))
    if path == "/api/kappa/backfill":
        if not day:
            raise ValueError("day is required")
        return 200, pipeline.locked(kappa_arch.backfill_day, day)
    if path == "/api/kappa/replay":
        return 200, pipeline.locked(kappa_arch.replay, one(q, "version", ""), one(q, "logic", "v2"))
    if path == "/api/kappa/swap":
        return 200, pipeline.locked(kappa_arch.swap, one(q, "version", ""))
    return None


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload).encode(), "application/json")

    def dispatch(self, routes):
        url = urlparse(self.path)
        try:
            result = routes(url.path, parse_qs(url.query))
            if result is None:
                self.send_json(404, {"error": "not found"})
            else:
                self.send_json(*result)
        except ValueError as e:
            self.send_json(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": str(e)})

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        self.dispatch(get_routes)

    def do_POST(self):
        self.dispatch(post_routes)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    pipeline.start_background()
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
