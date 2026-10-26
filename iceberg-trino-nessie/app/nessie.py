import json
import os
import urllib.parse
import urllib.request

NESSIE_URL = os.environ.get("NESSIE_URL", "http://localhost:20402")


def _call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(NESSIE_URL + "/api/v2" + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
        return json.loads(raw) if raw else {}


def refs():
    return [{"name": r["name"], "type": r["type"], "hash": r["hash"]} for r in _call("GET", "/trees")["references"]]


def ref(name):
    return _call("GET", "/trees/" + urllib.parse.quote(name))["reference"]


def create(name, kind, source):
    query = urllib.parse.urlencode({"name": name, "type": kind})
    return _call("POST", "/trees?" + query, ref(source))["reference"]


def merge(source, target, message):
    head = ref(target)["hash"]
    body = {"fromRefName": source, "fromHash": ref(source)["hash"], "message": message}
    return _call("POST", "/trees/%s@%s/history/merge" % (target, head), body)


def log(name, limit=50):
    entries = _call("GET", "/trees/%s/history?max-records=%d" % (urllib.parse.quote(name), limit))["logEntries"]
    return [{
        "hash": e["commitMeta"]["hash"],
        "parent": e.get("parentCommitHash"),
        "message": e["commitMeta"].get("message", ""),
        "author": e["commitMeta"].get("author", ""),
        "time": e["commitMeta"].get("commitTime", ""),
    } for e in entries]
