import json
import os
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import lakekeeper
from lake import revenue, revenue_sql, table_info

INDEX = os.path.join(os.path.dirname(__file__), "index.html")
LAKEKEEPER_UI = os.environ.get("LAKEKEEPER_UI", "http://localhost:26302/ui")


def catalog_info():
    server = lakekeeper.info()
    return {
        "lakekeeper_version": server.get("version"),
        "bootstrapped": server.get("bootstrapped"),
        "server_id": server.get("server-id"),
        "authz_backend": server.get("authz-backend"),
        "lakekeeper_ui": LAKEKEEPER_UI,
        "warehouses": [
            {"name": w["name"], "id": w["warehouse-id"], "status": w["status"], "bucket": w["storage-profile"].get("bucket"),
             "key_prefix": w["storage-profile"].get("key-prefix"), "sts_enabled": w["storage-profile"].get("sts-enabled")}
            for w in lakekeeper.warehouses()
        ],
        **table_info(),
    }


def revenue_at(snapshot_id):
    return {"snapshot_id": snapshot_id, "sql": revenue_sql(snapshot_id), "rows": revenue(snapshot_id)}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/":
                with open(INDEX, "rb") as f:
                    self.send(200, "text/html; charset=utf-8", f.read())
            elif url.path == "/api/revenue":
                self.json(revenue_at(parse_qs(url.query).get("snapshot", [None])[0]))
            elif url.path == "/api/catalog":
                self.json(catalog_info())
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
    port = int(os.environ.get("UI_PORT", "26304"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
