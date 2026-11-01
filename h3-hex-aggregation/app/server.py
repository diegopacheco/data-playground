import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import analysis
from data import CITIES, RESOLUTIONS

APP = Path(__file__).resolve().parent


def city_arg(query):
    city = query.get("city", ["sf"])[0]
    if city not in CITIES:
        raise ValueError(f"unknown city {city}")
    return city


def res_arg(query, default, allowed):
    res = int(query.get("res", [str(default)])[0])
    if res not in allowed:
        raise ValueError(f"resolution must be one of {allowed}")
    return res


ROUTES = {
    "/api/summary": lambda q: analysis.summary(),
    "/api/hexmap": lambda q: analysis.hexmap(city_arg(q), res_arg(q, 8, RESOLUTIONS)),
    "/api/rollup": lambda q: analysis.rollup(city_arg(q)),
    "/api/neighbours": lambda q: analysis.neighbours(city_arg(q)),
    "/api/region": lambda q: analysis.region(city_arg(q), res_arg(q, 9, [8, 9])),
    "/api/compare": lambda q: analysis.compare(city_arg(q)),
    "/api/compare-all": lambda q: analysis.compare_all(),
    "/api/crosscheck": lambda q: analysis.crosscheck(),
}


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
        url = urlparse(self.path)
        if url.path == "/":
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
            return
        route = ROUTES.get(url.path)
        if not route:
            self.send_json(404, {"error": "not found"})
            return
        try:
            self.send_json(200, route(parse_qs(url.query)))
        except ValueError as e:
            self.send_json(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    analysis.crosscheck()
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
