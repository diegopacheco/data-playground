import json
import os
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from lake import connect, rows

APP = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("UI_PORT", "21003"))
METADATA_TABLES = {
    "ducklake_snapshot": "snapshot_id",
    "ducklake_snapshot_changes": "snapshot_id",
    "ducklake_table": "table_id",
    "ducklake_column": "column_id",
    "ducklake_data_file": "data_file_id",
    "ducklake_delete_file": "delete_file_id",
    "ducklake_inlined_delete_1": "begin_snapshot, file_id, row_id",
    "ducklake_files_scheduled_for_deletion": "data_file_id",
}
CON = connect()


def revenue(cur, version):
    return rows(cur, f"""
        SELECT category, count(*) AS orders, sum(quantity) AS quantity, sum(quantity * price) AS revenue
        FROM lake.orders AT (VERSION => {int(version)}) GROUP BY category ORDER BY category
    """)


def table_exists(cur, version):
    return cur.execute(f"""
        SELECT count(*) FROM postgres_query('pg', 'SELECT table_id FROM ducklake_table
        WHERE table_name = ''orders'' AND begin_snapshot <= {int(version)}')
    """).fetchone()[0] > 0


def snapshots(cur):
    result = []
    for s in rows(cur, "SELECT snapshot_id, snapshot_time::VARCHAR AS snapshot_time, commit_message, changes FROM lake.snapshots() ORDER BY snapshot_id"):
        v = s["snapshot_id"]
        result.append({
            "snapshot_id": v,
            "snapshot_time": str(s["snapshot_time"]),
            "commit_message": s["commit_message"],
            "changes": s["changes"],
            "categories": revenue(cur, v) if table_exists(cur, v) else [],
        })
    return result


def metadata(cur):
    out = {}
    for table, key in METADATA_TABLES.items():
        out[table] = rows(cur, f"SELECT COLUMNS(*)::VARCHAR FROM postgres_query('pg', 'SELECT * FROM {table} ORDER BY {key} LIMIT 12')")
    return out


def columns(cur, version):
    return rows(cur, f"""
        SELECT column_name, column_type FROM postgres_query('pg', 'SELECT column_name, column_type, column_order
        FROM ducklake_column WHERE begin_snapshot <= {int(version)}
        AND (end_snapshot IS NULL OR end_snapshot > {int(version)}) ORDER BY column_order')
    """)


def encode(value):
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        cur = CON.cursor()
        routes = {
            "/api/snapshots": lambda: snapshots(cur),
            "/api/metadata": lambda: metadata(cur),
            "/api/revenue": lambda: revenue(cur, query.get("version", [latest(cur)])[0]),
            "/api/columns": lambda: columns(cur, query.get("version", [latest(cur)])[0]),
        }
        try:
            if url.path in routes:
                self.send(200, json.dumps(routes[url.path](), default=encode).encode(), "application/json")
            elif url.path == "/":
                with open(os.path.join(APP, "index.html"), "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            else:
                self.send(404, b'{"error":"not found"}', "application/json")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}).encode(), "application/json")
        finally:
            cur.close()


def latest(cur):
    return cur.execute("SELECT max(snapshot_id) FROM lake.snapshots()").fetchone()[0]


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
