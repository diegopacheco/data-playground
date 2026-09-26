import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import lance
import numpy as np

import vector
from bench import take_indices
from dataset import normalize
from formats import FORMATS

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "app" / "index.html"
LAKE = Path(os.environ.get("LAKE", ROOT / ".lake"))
RESULTS = Path(os.environ.get("RESULTS", ROOT / "results" / "results.json"))
PORT = int(os.environ.get("UI_PORT", "26800"))


def rows_in_lake():
    return lance.dataset(str(LAKE / "orders.lance")).count_rows()


def live_take(n, seed):
    indices = take_indices(rows_in_lake(), n, seed)
    out = []
    for fmt in FORMATS:
        start = time.perf_counter()
        table = fmt.take(LAKE / f"orders.{fmt.ext}", indices)
        ms = (time.perf_counter() - start) * 1000
        out.append({"name": fmt.name, "ms": round(ms, 3), "rows": table.num_rows, "table": normalize(table)})
    reference = out[0]["table"]
    for r in out:
        r["same_as_parquet"] = r.pop("table").equals(reference)
    return {"n": n, "seed": seed, "indices": indices[:10], "results": out,
            "sample": reference.slice(0, 5).drop_columns(["embedding"]).to_pylist()}


def live_nearest(order_id, k):
    path = LAKE / "orders.lance"
    row = lance.dataset(str(path)).take([order_id - 1], columns=["embedding", "product", "category"]).to_pylist()[0]
    query = np.asarray(row["embedding"], np.float32)
    timings = {}
    tables = {}
    for mode, use_index in (("ann", True), ("flat", False)):
        start = time.perf_counter()
        tables[mode] = vector.nearest(path, query, k, use_index)
        timings[mode] = round((time.perf_counter() - start) * 1000, 3)
    ann_ids = tables["ann"].column("order_id").to_pylist()
    flat_ids = tables["flat"].column("order_id").to_pylist()
    return {"order_id": order_id, "product": row["product"], "category": row["category"], "k": k,
            "ann_ms": timings["ann"], "flat_ms": timings["flat"],
            "recall": len(set(ann_ids) & set(flat_ids)) / k, "results": tables["ann"].to_pylist()}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                self.send(200, "text/html; charset=utf-8", PAGE.read_bytes())
            elif url.path == "/api/health":
                self.json(200, {"status": "UP"})
            elif url.path == "/api/results":
                if RESULTS.exists():
                    self.send(200, "application/json", RESULTS.read_bytes())
                else:
                    self.json(404, {"error": "results.json not found, run scripts/bench.sh"})
            elif url.path == "/api/take":
                n = max(1, min(int(query.get("n", "100")), 10000))
                self.json(200, live_take(n, int(query.get("seed", "99"))))
            elif url.path == "/api/nearest":
                self.json(200, live_nearest(int(query.get("order_id", "1")), max(1, min(int(query.get("k", "10")), 100))))
            else:
                self.json(404, {"error": "not found"})
        except (ValueError, IndexError, OSError) as e:
            self.json(400, {"error": str(e)})

    def json(self, code, body):
        self.send(code, "application/json", json.dumps(body, default=str).encode())

    def send(self, code, kind, body):
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
