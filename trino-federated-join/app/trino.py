import json
import os
import urllib.request

TRINO_URL = os.environ.get("TRINO_URL", "http://localhost:23505")


def call(method, url, body=None):
    req = urllib.request.Request(url, data=body, method=method, headers={"X-Trino-User": "i35", "Content-Type": "text/plain"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def query(sql):
    page = call("POST", TRINO_URL + "/v1/statement", sql.encode())
    columns, rows = [], []
    while True:
        if "error" in page:
            raise RuntimeError(page["error"].get("message", "trino error"))
        if page.get("columns") and not columns:
            columns = [c["name"] for c in page["columns"]]
        rows.extend(page.get("data", []))
        if "nextUri" not in page:
            return columns, rows
        page = call("GET", page["nextUri"])
