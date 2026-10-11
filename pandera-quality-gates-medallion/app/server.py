import json
import os
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import platform
from contracts import describe
from pipeline import LAYERS, Pipeline, Rejected

HERE = Path(__file__).parent
PORT = int(os.environ.get("UI_PORT", "8080"))
pipeline = Pipeline(os.environ.get("WAREHOUSE", "/app/warehouse/lake.duckdb"), os.environ.get("INCOMING", "/data/incoming"))
STACK = {"python": platform.python_version(), **{p: version(p) for p in ["pandera", "pandas", "duckdb"]}}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        query = parse_qs(url.query)
        if not parts:
            return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if parts == ["api", "health"]:
            return self.send(200, {"status": "ok"})
        if parts == ["api", "summary"]:
            return self.send(200, {**pipeline.summary(), "stack": STACK})
        if parts == ["api", "contracts"]:
            return self.send(200, describe())
        if parts == ["api", "batches"]:
            return self.send(200, pipeline.batches())
        if len(parts) == 3 and parts[:2] == ["api", "batches"]:
            report = pipeline.batch(parts[2])
            return self.send(200, report) if report else self.send(404, {"error": f"batch {parts[2]} not found"})
        if parts == ["api", "incoming"]:
            return self.send(200, pipeline.incoming_files())
        if len(parts) == 3 and parts[:2] == ["api", "incoming"]:
            text = pipeline.incoming_csv(parts[2])
            return self.send(200, text.encode(), "text/csv") if text else self.send(404, {"error": f"incoming {parts[2]} not found"})
        if len(parts) == 3 and parts[:2] == ["api", "layers"] and parts[2] in LAYERS:
            limit = int(query.get("limit", ["100"])[0])
            return self.send(200, pipeline.layer(parts[2], limit))
        self.send(404, {"error": "not found"})

    def do_POST(self):
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if parts == ["api", "pipeline", "run"]:
            return self.send(200, pipeline.run_all())
        if parts == ["api", "batches"]:
            try:
                body = json.loads(raw)
                report = pipeline.ingest(body.get("batch_id", ""), body.get("extracted_at") or datetime.now().isoformat(timespec="seconds"), body.get("csv", ""))
            except Rejected as e:
                return self.send(409, {"error": str(e)})
            except ValueError as e:
                return self.send(400, {"error": str(e)})
            return self.send(201, report)
        self.send(404, {"error": "not found"})


if __name__ == "__main__":
    summary = pipeline.run_all()
    for b in summary["batches"]:
        print(f"{b['batch_id']} {b['status']} {b['blocked_at'] or ''} failed={len(b['failed_checks'])}", flush=True)
    print(f"layers {summary['layers']} ui on port {PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
