import json
import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import gravitino
import marquez
import warehouse
from model import METALAKE, JOB_NAMESPACE

INDEX = os.path.join(os.path.dirname(__file__), "index.html")
GRAVITINO_WEB = os.environ.get("GRAVITINO_WEB", "http://localhost:27100")
MARQUEZ_WEB = os.environ.get("MARQUEZ_WEB", "http://localhost:27102")


def info():
    return {
        "gravitino_version": gravitino.version(), "metalake": METALAKE, "job_namespace": JOB_NAMESPACE,
        "links": {
            "gravitino_ui": GRAVITINO_WEB,
            "gravitino_api": f"{GRAVITINO_WEB}/api/metalakes/{METALAKE}",
            "marquez_ui": f"{MARQUEZ_WEB}/lineage/dataset/{METALAKE}/{marquez.ROOT_NODE.split(':', 2)[2]}",
            "marquez_jobs": f"{MARQUEZ_WEB}/jobs",
        },
    }


ROUTES = {
    "/api/info": info,
    "/api/catalog": gravitino.tree,
    "/api/runs": marquez.pipeline_runs,
    "/api/lineage": marquez.graph,
    "/api/revenue": warehouse.revenue,
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/":
                with open(INDEX, "rb") as f:
                    self.send(200, "text/html; charset=utf-8", f.read())
            elif path in ROUTES:
                self.json(ROUTES[path]())
            else:
                self.json({"error": "not found"}, 404)
        except Exception as e:
            self.json({"error": str(e)}, 500)

    def json(self, body, status=200):
        self.send(status, "application/json", json.dumps(body, default=str).encode())

    def send(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("UI_PORT", "8080"))), Handler).serve_forever()
