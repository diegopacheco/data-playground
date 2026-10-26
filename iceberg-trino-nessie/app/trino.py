import json
import os
import urllib.request

TRINO_URL = os.environ.get("TRINO_URL", "http://localhost:20403")


def _call(method, url, body=None):
    request = urllib.request.Request(url, data=body, method=method, headers={"X-Trino-User": "i4"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def query(sql):
    result = _call("POST", TRINO_URL + "/v1/statement", sql.encode())
    columns, rows = None, []
    while True:
        if "error" in result:
            raise RuntimeError(result["error"]["message"])
        if columns is None and result.get("columns"):
            columns = [c["name"] for c in result["columns"]]
        rows.extend(result.get("data", []))
        next_uri = result.get("nextUri")
        if not next_uri:
            return [dict(zip(columns or [], row)) for row in rows]
        result = _call("GET", next_uri)


def ready():
    info = _call("GET", TRINO_URL + "/v1/info")
    return not info.get("starting", True)
