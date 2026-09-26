import json
import os
import urllib.error
import urllib.request

URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = "products"


def call(method, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path} returned {e.code}: {e.read().decode()}") from None


def collection(path=""):
    return f"/collections/{COLLECTION}{path}"


def query(body):
    return call("POST", collection("/points/query"), body)["result"]["points"]
