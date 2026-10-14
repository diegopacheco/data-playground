import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from vault import connect, rows

APP = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("UI_PORT", "30900"))
LAYERS = ("raw_vault", "business_vault", "mart")


def model(con):
    tables = rows(con, f"""
        SELECT table_schema AS layer, table_name AS name, split_part(table_name, '_', 1) AS kind,
               list(column_name ORDER BY ordinal_position) AS columns
        FROM information_schema.columns WHERE table_schema IN {LAYERS}
        GROUP BY ALL
    """)
    tables.sort(key=lambda t: (LAYERS.index(t["layer"]), t["name"]))
    for t in tables:
        t["rows"] = con.execute(f'SELECT count(*) FROM {t["layer"]}.{t["name"]}').fetchone()[0]
    vault = [t for t in tables if t["layer"] == "raw_vault"]
    owners = {t["columns"][0]: t["name"] for t in vault if t["kind"] in ("hub", "link")}
    edges = [{"from": t["name"], "to": owners[c], "key": c}
             for t in vault for c in t["columns"] if c in owners and owners[c] != t["name"]]
    return {"tables": tables, "edges": edges}


def batches(con):
    return rows(con, """
        SELECT load_date, table_name, split_part(table_name, '_', 1) AS kind, delivered_rows, total_rows,
               total_rows - coalesce(lag(total_rows) OVER (PARTITION BY table_name ORDER BY load_date), 0) AS added_rows
        FROM audit.load_audit ORDER BY load_date, position
    """)


def customers(con):
    return rows(con, """
        SELECT hub.customer_id,
               (SELECT count(*) FROM raw_vault.sat_customer_contact s WHERE s.customer_hk = hub.customer_hk) AS contact_versions,
               (SELECT count(*) FROM raw_vault.sat_customer_profile s WHERE s.customer_hk = hub.customer_hk) AS profile_versions
        FROM raw_vault.hub_customer hub ORDER BY hub.customer_id
    """)


def history(con, customer_id):
    def satellite(name):
        return rows(con, f"""
            SELECT sat.* FROM raw_vault.{name} sat JOIN raw_vault.hub_customer hub USING (customer_hk)
            WHERE hub.customer_id = ? ORDER BY sat.load_date
        """, [customer_id])
    return {
        "customer_id": customer_id,
        "hub": rows(con, "SELECT * FROM raw_vault.hub_customer WHERE customer_id = ?", [customer_id]),
        "sat_customer_contact": satellite("sat_customer_contact"),
        "sat_customer_profile": satellite("sat_customer_profile"),
        "as_of": rows(con, "SELECT * EXCLUDE (customer_hk) FROM business_vault.customer_as_of WHERE customer_id = ? ORDER BY as_of_date", [customer_id]),
    }


def mart(con):
    return {
        "totals": rows(con, """
            SELECT count(*) AS order_lines, count(DISTINCT order_id) AS orders, sum(quantity) AS quantity, sum(revenue) AS revenue
            FROM mart.fct_order_lines
        """)[0],
        "revenue": rows(con, """
            SELECT p.category, c.segment, count(*) AS order_lines, sum(f.quantity) AS quantity, sum(f.revenue) AS revenue
            FROM mart.fct_order_lines f JOIN mart.dim_product p USING (product_hk) JOIN mart.dim_customer c USING (customer_hk)
            GROUP BY ALL ORDER BY p.category, c.segment
        """),
        "lines": rows(con, """
            SELECT f.order_id, f.line_no, f.order_date, f.status, c.customer_id, c.name AS customer, c.segment,
                   p.name AS product, p.category, f.quantity, f.unit_price, f.revenue
            FROM mart.fct_order_lines f JOIN mart.dim_product p USING (product_hk) JOIN mart.dim_customer c USING (customer_hk)
            ORDER BY f.revenue DESC, f.order_id, f.line_no LIMIT 12
        """),
    }


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, kind):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        routes = {
            "/api/model": model,
            "/api/batches": batches,
            "/api/customers": customers,
            "/api/history": lambda con: history(con, query.get("customer_id", ["C020"])[0]),
            "/api/mart": mart,
        }
        try:
            if url.path in routes:
                con = connect()
                try:
                    body = json.dumps(routes[url.path](con), default=float_or_text).encode()
                finally:
                    con.close()
                self.send(200, body, "application/json")
            elif url.path == "/":
                with open(os.path.join(APP, "index.html"), "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            else:
                self.send(404, b'{"error":"not found"}', "application/json")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}).encode(), "application/json")


def float_or_text(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
