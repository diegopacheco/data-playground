import copy
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import opa
from cases import CASES, USERS, compare
from trino import attempt

APP = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("UI_PORT", "30403"))
CUSTOMERS = "postgres.public.customers"
CHANGE_USER = "bruno"
CHANGE_SQL = "SELECT customer_id, name, email, national_id, phone FROM customers ORDER BY customer_id LIMIT 3"
DECISION_SQL = "SELECT customer_id, email, phone, country FROM customers ORDER BY customer_id LIMIT 2"


def users():
    data = opa.read_data()
    out = []
    for name in USERS:
        role = data["users"].get(name, {}).get("role")
        out.append({"user": name, "role": role, "country": data["users"].get(name, {}).get("country"),
                    "policy": data["roles"].get(role)})
    return out


def cases():
    return [{"case": key, "title": case["title"]} for key, case in CASES.items()]


def policy_change():
    original = opa.file_data()
    changed = copy.deepcopy(original)
    changed["roles"]["analyst"]["masks"][CUSTOMERS]["email"] = "null"
    started = opa.trino_started()
    before = attempt(CHANGE_SQL, CHANGE_USER)
    opa.write_data(changed)
    try:
        after = attempt(CHANGE_SQL, CHANGE_USER)
    finally:
        opa.write_data(original)
    return {
        "user": CHANGE_USER,
        "sql": CHANGE_SQL,
        "change": f'roles.analyst.masks["{CUSTOMERS}"].email: "email" -> "null"',
        "before": before,
        "after": after,
        "restored": attempt(CHANGE_SQL, CHANGE_USER),
        "trino_started_before": started,
        "trino_started_after": opa.trino_started(),
    }


def decisions(user):
    result = attempt(DECISION_SQL, user)
    return {"user": user, "sql": DECISION_SQL, "result": result,
            "decisions": opa.decisions(result["query_id"]) if "query_id" in result else []}


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
        routes = {
            "/api/users": users,
            "/api/cases": cases,
            "/api/compare": lambda: compare(query.get("case", ["columns"])[0]),
            "/api/policy-change": policy_change,
            "/api/decisions": lambda: decisions(query.get("user", ["rita"])[0]),
        }
        try:
            if url.path in routes:
                self.send(200, json.dumps(routes[url.path]()).encode(), "application/json")
            elif url.path == "/":
                with open(os.path.join(APP, "index.html"), "rb") as f:
                    self.send(200, f.read(), "text/html; charset=utf-8")
            else:
                self.send(404, b'{"error":"not found"}', "application/json")
        except Exception as e:
            self.send(500, json.dumps({"error": str(e)}).encode(), "application/json")

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
