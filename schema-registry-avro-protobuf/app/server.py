import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from confluent_kafka.admin import AdminClient

import flow
import matrix
import registry

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("UI_PORT", "8080"))
LOCK = threading.Lock()
STATE = {"matrix": None, "flow": None, "ran_at": None, "error": None}


def run_all():
    with LOCK:
        started = time.time()
        try:
            STATE["matrix"] = matrix.run()
            STATE["flow"] = flow.run()
            STATE["ran_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            STATE["took_ms"] = round((time.time() - started) * 1000)
            STATE["error"] = None
        except Exception as e:
            STATE["error"] = f"{type(e).__name__}: {e}"
            raise
    return summary()


def summary():
    m = STATE["matrix"]
    counts = {}
    if m:
        for fmt in matrix.TYPES:
            for row in m[fmt]["changes"]:
                for mode, r in row["results"].items():
                    key = f"{fmt}.{mode}"
                    counts.setdefault(key, {"accepted": 0, "rejected": 0})
                    counts[key]["accepted" if r["accepted"] else "rejected"] += 1
    f = STATE["flow"] or {}
    return {"ran_at": STATE["ran_at"], "took_ms": STATE.get("took_ms"), "error": STATE["error"], "verdicts": counts,
            "messages": {fmt: len(v["messages"]) for fmt, v in f.items()}}


def kafka_status():
    try:
        meta = AdminClient({"bootstrap.servers": flow.BOOTSTRAP}).list_topics(timeout=5)
        return {"up": True, "brokers": len(meta.brokers), "topics": sorted(t for t in meta.topics if not t.startswith("__"))}
    except Exception as e:
        return {"up": False, "error": str(e)}


def registry_view():
    out = {}
    for group in (matrix.GROUP, flow.GROUP):
        items = []
        for a in registry.artifacts(group):
            vs = registry.versions(group, a["artifactId"])
            items.append({"artifact": a["artifactId"], "type": a["artifactType"], "rule": registry.rule(group, a["artifactId"]),
                          "versions": [{"version": v["version"], "global_id": v["globalId"], "content_id": v["contentId"], "created": v["createdOn"],
                                        "content": registry.version_content(group, a["artifactId"], v["version"])} for v in vs]})
        out[group] = items
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def guarded(self, fn):
        try:
            self.send(200, fn())
        except Exception as e:
            self.send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                return self.send(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/status":
            return self.guarded(lambda: {"registry": registry.info(), "kafka": kafka_status(), **summary()})
        if path in ("/api/matrix", "/api/flow"):
            key = path.rsplit("/", 1)[1]
            if STATE[key] is None:
                return self.send(404, {"error": "nothing ran yet, POST /api/run first"})
            return self.send(200, STATE[key])
        if path == "/api/registry":
            return self.guarded(registry_view)
        self.send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/run":
            return self.guarded(run_all)
        if path == "/api/check":
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
            if body.get("format") not in matrix.TYPES or body.get("mode") not in matrix.catalog()["modes"] or not body.get("schema"):
                return self.send(400, {"error": "format (avro|protobuf), mode (BACKWARD|FORWARD|FULL|NONE) and schema are required"})
            return self.guarded(lambda: matrix.try_change(body["format"], body["mode"], body["schema"]))
        self.send(404, {"error": "not found"})


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
