import json
import os
import urllib.request

TRINO_URL = os.environ.get("TRINO_URL", "http://localhost:30402")


def call(method, url, user, body=None):
    headers = {"X-Trino-User": user, "X-Trino-Catalog": "postgres", "X-Trino-Schema": "public", "Content-Type": "text/plain"}
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def query(sql, user):
    page = call("POST", TRINO_URL + "/v1/statement", user, sql.encode())
    result = {"query_id": page["id"], "columns": [], "rows": []}
    while True:
        if "error" in page:
            raise RuntimeError(page["error"].get("message", "trino error"))
        if page.get("columns") and not result["columns"]:
            result["columns"] = [c["name"] for c in page["columns"]]
        result["rows"].extend(page.get("data", []))
        if "nextUri" not in page:
            return result
        page = call("GET", page["nextUri"], user)


def attempt(sql, user):
    try:
        return query(sql, user)
    except RuntimeError as e:
        return {"error": str(e)}
