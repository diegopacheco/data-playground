import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pyiceberg.exceptions import NoSuchTableError

from i36_pipeline import lake

TABLES = ["raw_orders", "clean_orders", "revenue_by_category"]
INDEX = Path(__file__).with_name("index.html").read_bytes()


def revenue():
    table = lake.read_table("revenue_by_category")
    rows = table.scan().to_arrow().sort_by([("revenue", "descending")]).to_pylist()
    return {"snapshot_id": str(table.current_snapshot().snapshot_id), "rows": rows}


def table_info(name):
    table = lake.read_table(name)
    return {
        "table": f"{lake.NAMESPACE}.{name}",
        "rows": table.scan().to_arrow().num_rows,
        "snapshots": len(table.snapshots()),
        "current_snapshot": str(table.current_snapshot().snapshot_id),
        "columns": [f.name for f in table.schema().fields],
    }


ROUTES = {
    "/api/revenue": revenue,
    "/api/tables": lambda: [table_info(n) for n in TABLES],
}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self.send(200, INDEX, "text/html; charset=utf-8")
        route = ROUTES.get(self.path)
        if route is None:
            return self.send(404, b'{"error":"not found"}', "application/json")
        try:
            return self.send(200, json.dumps(route()).encode(), "application/json")
        except NoSuchTableError:
            return self.send(404, b'{"error":"tables not materialized yet"}', "application/json")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("UI_PORT", "8080"))), Handler).serve_forever()
