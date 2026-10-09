import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db
from embed import embed_query, model, to_pg

INDEX = Path(__file__).resolve().parent / "index.html"
LOCK = threading.Lock()


def search(params):
    text = params.get("q", [""])[0].strip()
    if not text:
        raise ValueError("q is required")
    mode = params.get("mode", ["vector"])[0]
    category = params.get("category", [""])[0] or None
    k = max(1, min(int(params.get("k", ["5"])[0]), 30))
    start = time.perf_counter()
    with LOCK:
        vector = to_pg(embed_query(text))
    embed_ms = (time.perf_counter() - start) * 1000
    sql = db.HYBRID_SEARCH if mode == "hybrid" else db.VECTOR_SEARCH
    start = time.perf_counter()
    with db.connect() as conn:
        hits = db.rows(conn, sql, {"q": vector, "text": text, "category": category, "k": k})
    query_ms = (time.perf_counter() - start) * 1000
    for h in hits:
        for key in ("score", "cosine", "rank"):
            if h.get(key) is not None:
                h[key] = round(float(h[key]), 4)
    return {"query": text, "mode": "hybrid" if mode == "hybrid" else "vector", "category": category,
            "embed_ms": round(embed_ms, 2), "query_ms": round(query_ms, 2), "results": hits}


def pipeline():
    with db.connect() as conn:
        out = db.load_results(conn) or {}
        out["categories"] = [r["category"] for r in db.rows(conn, "SELECT DISTINCT category FROM products ORDER BY 1")]
        out["embedded_products"] = db.rows(conn, "SELECT count(*) AS n FROM products WHERE embedding IS NOT NULL")[0]["n"]
    return out


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/":
                self.send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/search":
                self.send(200, search(parse_qs(url.query)))
            elif url.path == "/api/pipeline":
                self.send(200, pipeline())
            else:
                self.send(404, {"error": "not found"})
        except ValueError as e:
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": str(e)})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    model()
    port = int(os.environ.get("UI_PORT", "24801"))
    print(f"listening on {port}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
