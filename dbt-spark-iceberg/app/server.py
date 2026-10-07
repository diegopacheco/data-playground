import json
import os
from decimal import Decimal
from datetime import datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from pyhive import hive

THRIFT_HOST = os.environ.get("THRIFT_HOST", "localhost")
THRIFT_PORT = int(os.environ.get("THRIFT_PORT", "23900"))
UI_PORT = int(os.environ.get("UI_PORT", "23980"))
INDEX = Path(__file__).with_name("index.html")

QUERIES = {
    "/api/revenue": """
        select category, total_orders, total_quantity, total_revenue
        from analytics.revenue_by_category order by total_revenue desc""",
    "/api/snapshots": """
        select cast(snapshot_id as string) as snapshot_id, cast(committed_at as string) as committed_at,
               operation, summary['added-records'] as added_records,
               summary['deleted-records'] as deleted_records, summary['total-records'] as total_records
        from analytics.fct_orders.snapshots order by committed_at""",
    "/api/loads": """
        select cast(loaded_at as string) as loaded_at, count(*) as orders, min(order_id) as first_order,
               max(order_id) as last_order
        from analytics.fct_orders group by loaded_at order by loaded_at""",
    "/api/orders": """
        select order_id, customer, product, category, quantity, price, amount, cast(ts as string) as ts
        from analytics.fct_orders order by ts desc limit 15""",
}


def to_json(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def run_query(sql):
    conn = hive.connect(host=THRIFT_HOST, port=THRIFT_PORT)
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        names = [d[0].split(".")[-1] for d in cursor.description]
        return [{n: to_json(v) for n, v in zip(names, row)} for row in cursor.fetchall()]
    finally:
        conn.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self.reply(200, "text/html; charset=utf-8", INDEX.read_bytes())
        elif path in QUERIES:
            try:
                body = json.dumps(run_query(QUERIES[path])).encode()
                self.reply(200, "application/json", body)
            except Exception as e:
                self.reply(500, "application/json", json.dumps({"error": str(e)[:500]}).encode())
        else:
            self.reply(404, "application/json", b'{"error":"not found"}')

    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"ui listening on http://localhost:{UI_PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", UI_PORT), Handler).serve_forever()
