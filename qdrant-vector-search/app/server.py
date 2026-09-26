import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import embed
import qdrant
import search

INDEX = Path(__file__).with_name("index.html").read_bytes()
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:6333/dashboard")


def number(params, name, cast=float):
    value = params.get(name, [""])[0].strip()
    return cast(value) if value else None


def filters(params, exclude_id=None):
    return search.build_filter(
        category=params.get("category", [""])[0] or None,
        price_min=number(params, "price_min"),
        price_max=number(params, "price_max"),
        min_rating=number(params, "min_rating"),
        in_stock=params.get("in_stock", [""])[0] == "true",
        exclude_id=exclude_id,
    )


def info():
    collection = qdrant.call("GET", qdrant.collection())["result"]
    facets = qdrant.call("POST", qdrant.collection("/facet"), {"key": "category", "limit": 20, "exact": True})["result"]["hits"]
    return {
        "qdrant_version": qdrant.call("GET", "/")["version"],
        "collection": qdrant.COLLECTION,
        "status": collection["status"],
        "points_count": collection["points_count"],
        "vectors": collection["config"]["params"]["vectors"],
        "sparse_vectors": collection["config"]["params"]["sparse_vectors"],
        "payload_schema": {k: v["data_type"] for k, v in collection["payload_schema"].items()},
        "categories": [{"category": f["value"], "count": f["count"]} for f in facets],
        "dense_model": embed.DENSE_MODEL,
        "sparse_model": embed.SPARSE_MODEL,
        "dashboard_url": DASHBOARD_URL,
    }


def api(url):
    params = parse_qs(url.query)
    limit = number(params, "limit", int) or 8
    if url.path == "/api/info":
        return info()
    if url.path == "/api/search":
        text = params.get("q", [""])[0].strip()
        mode = params.get("mode", ["semantic"])[0]
        if not text or mode not in search.MODES:
            raise ValueError(f"q is required and mode must be one of {search.MODES}")
        return search.search(text, mode, filters(params), limit)
    if url.path == "/api/recommend":
        point_id = number(params, "id", int)
        if point_id is None:
            raise ValueError("id is required")
        return search.recommend(point_id, filters(params, exclude_id=point_id), limit)
    return None


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            return self.reply(200, "text/html; charset=utf-8", INDEX)
        try:
            body = api(url)
            if body is None:
                return self.reply(404, "application/json", b'{"error": "not found"}')
            self.reply(200, "application/json", json.dumps(body).encode())
        except ValueError as e:
            self.reply(400, "application/json", json.dumps({"error": str(e)}).encode())
        except Exception as e:
            self.reply(500, "application/json", json.dumps({"error": str(e)}).encode())

    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    embed.warm()
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"serving on port {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
