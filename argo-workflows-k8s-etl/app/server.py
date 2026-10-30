import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import argo
import warehouse

APP = Path(__file__).resolve().parent
ARGO = argo.Argo(os.environ.get("ARGO_URL", "http://argo-server.argo:2746"), os.environ.get("NAMESPACE", "t8-etl"))
PARAMS = ("seed", "rows", "alert_cents", "big_cents", "fail_region")


def workflows():
    items = sorted(ARGO.workflows(), key=lambda w: w["metadata"].get("creationTimestamp", ""), reverse=True)
    return [argo.summary(w) for w in items]


def workflow(name):
    wf = ARGO.workflow(name)
    return dict(argo.summary(wf), steps=argo.steps(wf))


def cron():
    c = ARGO.cron()
    return {
        "name": c["metadata"]["name"],
        "schedules": c["spec"].get("schedules") or [c["spec"].get("schedule")],
        "concurrency": c["spec"].get("concurrencyPolicy"),
        "suspended": bool(c["spec"].get("suspend")),
        "last_scheduled": (c.get("status") or {}).get("lastScheduledTime"),
        "active": len((c.get("status") or {}).get("active") or []),
        "succeeded": (c.get("status") or {}).get("succeeded", 0),
        "failed": (c.get("status") or {}).get("failed", 0),
    }


def submit(query):
    params = {k: query[k][0] for k in PARAMS if k in query}
    return {"name": ARGO.submit("WorkflowTemplate", argo.TEMPLATE, params)}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload).encode(), "application/json")

    def guarded(self, fn, *args):
        try:
            self.send_json(200, fn(*args))
        except Exception as e:
            traceback.print_exc()
            self.send_json(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        parts = urlparse(self.path).path.strip("/").split("/")
        if parts == [""]:
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif parts == ["api", "workflows"]:
            self.guarded(workflows)
        elif len(parts) == 3 and parts[:2] == ["api", "workflows"]:
            self.guarded(workflow, parts[2])
        elif parts == ["api", "cron"]:
            self.guarded(cron)
        elif parts == ["api", "batches"]:
            self.guarded(warehouse.batches)
        elif len(parts) == 3 and parts[:2] == ["api", "batches"]:
            self.guarded(warehouse.batch_detail, parts[2])
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path == "/api/submit":
            self.guarded(submit, parse_qs(url.query))
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
