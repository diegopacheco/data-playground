import datetime
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import s3
import streams

APP = Path(__file__).resolve().parent
DATA_FILE = Path(os.environ.get("DATA_FILE", "/data/orders.jsonl"))
PROOF = Path(os.environ.get("PROOF", "/app/results/proof.json"))
TOPIC = os.environ.get("TOPIC", "orders")
BUCKETS = [os.environ.get("DATA_BUCKET", "r9-automq-data"), os.environ.get("OPS_BUCKET", "r9-automq-ops")]
MINIO_CONSOLE = os.environ.get("MINIO_CONSOLE_URL", "http://localhost:27401")
LOCK = threading.Lock()


def now():
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def lines():
    return [line.encode() for line in DATA_FILE.read_text().splitlines() if line]


def storage():
    return {"buckets": [s3.summary(bucket) for bucket in BUCKETS]}


def storage_totals():
    report = storage()
    return {b["bucket"]: {"objects": b["objects"], "bytes": b["bytes"]} for b in report["buckets"]}


def load_proof():
    return json.loads(PROOF.read_text()) if PROOF.exists() else {"events": []}


def save_proof(proof):
    PROOF.parent.mkdir(parents=True, exist_ok=True)
    PROOF.write_text(json.dumps(proof, indent=1))


def event(proof, step, title, detail):
    proof["events"].append({"step": step, "title": title, "at": now(), "detail": detail, "cluster": streams.cluster(), "storage": storage_totals()})


def run_produce():
    with LOCK:
        records = lines()
        streams.recreate_topic(TOPIC)
        since = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        produced = streams.produce(TOPIC, records)
        produced["s3_written"] = s3.written_since(BUCKETS[0], since)
        proof = {"topic": TOPIC, "started_at": now(), "input": {"file": DATA_FILE.name, "records": len(records)}, "produced": produced, "events": []}
        event(proof, "produce", f"produced {produced['records']} records with acks=all", produced)
        save_proof(proof)
        return proof


def run_consume():
    with LOCK:
        proof = load_proof()
        result = streams.consume(TOPIC)
        values = result.pop("values")
        expected = sorted(lines())
        result["missing"] = len(set(expected) - set(values))
        result["duplicates"] = len(values) - len(set(values))
        result["matches_input"] = sorted(values) == expected
        proof["consumed"] = result
        event(proof, "consume", f"consumed {result['records']} records from offset 0 with a new consumer group", result)
        save_proof(proof)
        return proof


def add_event(body):
    with LOCK:
        proof = load_proof()
        event(proof, body["step"], body["title"], body.get("detail", {}))
        save_proof(proof)
        return proof


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload).encode(), "application/json")

    def answer(self, action):
        try:
            self.send_json(200, action())
        except Exception as error:
            self.send_json(500, {"error": f"{type(error).__name__}: {error}"})

    def do_GET(self):
        routes = {
            "/api/health": lambda: {"status": "ok"},
            "/api/cluster": streams.cluster,
            "/api/storage": storage,
            "/api/proof": lambda: {**load_proof(), "minio_console": MINIO_CONSOLE},
        }
        if self.path == "/":
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path in routes:
            self.answer(routes[self.path])
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        routes = {"/api/produce": run_produce, "/api/consume": run_consume, "/api/events": lambda: add_event(body)}
        if self.path in routes:
            self.answer(routes[self.path])
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    for bucket in BUCKETS:
        s3.make_bucket(bucket)
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
