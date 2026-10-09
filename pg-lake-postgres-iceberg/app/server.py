import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import lake

APP = Path(__file__).resolve().parent
WRITE_LOCK = threading.Lock()
HISTORY = []
MAX_HISTORY = 12
MINIO_CONSOLE = os.environ.get("MINIO_CONSOLE_URL", "http://localhost:27602")


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send(status, json.dumps(payload, default=str).encode(), "application/json")

    def answer(self, action, name=None):
        entry = {"action": name, "at": int(time.time() * 1000)}
        try:
            if name:
                with WRITE_LOCK:
                    entry["result"] = action()
            else:
                entry["result"] = action()
            self.send_json(200, entry["result"])
        except lake.LakeError as e:
            entry["error"] = str(e)
            self.send_json(e.status, {"error": str(e)})
        except Exception as e:
            traceback.print_exc()
            entry["error"] = str(e).strip()
            self.send_json(500, {"error": entry["error"]})
        if name:
            HISTORY.append(entry)
            del HISTORY[:-MAX_HISTORY]

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/":
            self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/status":
            self.answer(lambda: {**lake.status(), "minioConsole": MINIO_CONSOLE, "history": HISTORY})
        elif url.path == "/api/lake":
            self.answer(lake.lake)
        elif url.path.startswith("/api/query/"):
            self.answer(lambda: lake.query(url.path.rsplit("/", 1)[1]))
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        url = urlsplit(self.path)
        params = parse_qs(url.query)
        if url.path == "/api/reset":
            self.answer(lake.reset, "reset")
        elif url.path == "/api/load":
            batch = params.get("batch", [""])[0]
            if not batch.isdigit():
                self.send_json(400, {"error": "batch must be a number"})
                return
            self.answer(lambda: lake.load(int(batch)), f"load batch {batch}")
        elif url.path == "/api/delete-cancelled":
            self.answer(lake.delete_cancelled, "delete cancelled")
        elif url.path == "/api/run":
            self.answer(lake.run, "run all")
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
