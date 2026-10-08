import json
import os
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))

from store import load_all

API = os.environ["PREFECT_API_URL"]
PAGE = Path(__file__).resolve().parent / "index.html"
ORDER = {"extract": 0, "transform": 1, "load": 2}


def prefect_post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def runs(limit=10):
    flows = prefect_post("/flow_runs/filter", {
        "flows": {"name": {"any_": ["revenue-etl"]}},
        "flow_runs": {"state": {"type": {"not_any_": ["SCHEDULED"]}}},
        "sort": "START_TIME_DESC",
        "limit": limit,
    })
    ids = [f["id"] for f in flows]
    tasks = prefect_post("/task_runs/filter", {"flow_runs": {"id": {"any_": ids}}}) if ids else []
    by_flow = {}
    for t in tasks:
        by_flow.setdefault(t["flow_run_id"], []).append({
            "task": t["task_key"].split("-")[0],
            "state": t["state"]["name"] if t.get("state") else None,
            "run_count": t["run_count"],
        })
    return [
        {
            "id": f["id"],
            "name": f["name"],
            "deployment_id": f.get("deployment_id"),
            "state": f["state"]["name"] if f.get("state") else None,
            "start_time": f.get("start_time"),
            "tasks": sorted(by_flow.get(f["id"], []), key=lambda t: ORDER.get(t["task"], 9)),
        }
        for f in flows
    ]


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        try:
            if path == "/":
                self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/revenue":
                self.send(200, json.dumps(load_all()).encode(), "application/json")
            elif path == "/api/runs":
                self.send(200, json.dumps(runs()).encode(), "application/json")
            elif path == "/api/config":
                self.send(200, json.dumps({"prefect_ui": API.removesuffix("/api")}).encode(), "application/json")
            else:
                self.send(404, b'{"error":"not found"}', "application/json")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ["UI_PORT"])), Handler).serve_forever()
