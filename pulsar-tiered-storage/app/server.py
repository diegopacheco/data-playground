import csv
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pulsar

ADMIN = os.environ.get("ADMIN_URL", "http://r7-broker:8080")
SERVICE = os.environ.get("PULSAR_URL", "pulsar://r7-broker:6650")
BOOKIE = os.environ.get("BOOKIE_URL", "http://r7-bookie:8000")
S3 = os.environ.get("S3_URL", "http://r7-minio:9000")
BUCKET = os.environ.get("BUCKET", "pulsar-offload")
CLUSTER = os.environ.get("CLUSTER", "r7-cluster")
TOPIC = os.environ.get("TOPIC", "persistent://public/default/readings")
DATA = Path(os.environ.get("DATA_DIR", "/app/data"), "readings.csv")
INDEX = Path(__file__).with_name("index.html")
PORT = int(os.environ.get("UI_PORT", "8080"))
TOPIC_PATH = TOPIC.replace("://", "/")
BROKER_KEYS = ["managedLedgerOffloadDriver",
               "managedLedgerOffloadDeletionLagMs", "managedLedgerMaxEntriesPerLedger", "managedLedgerMinLedgerRolloverTimeMinutes",
               "managedLedgerDefaultEnsembleSize", "managedLedgerDefaultWriteQuorum", "managedLedgerCacheSizeMB",
               "defaultRetentionTimeInMinutes", "defaultRetentionSizeInMB", "retentionCheckIntervalInSeconds"]
LOCK = threading.Lock()
CLIENT = pulsar.Client(SERVICE, operation_timeout_seconds=30)


class HttpError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def call(method, url, body=None, raw=False):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = r.read()
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode(errors="replace") or str(e))
    if raw:
        return payload
    return json.loads(payload) if payload else None


def admin(method, path, body=None):
    return call(method, f"{ADMIN}/admin/v2/{path}", body)


def csv_rows():
    with DATA.open() as f:
        return [row for row in csv.reader(f)][1:]


def expected():
    rows = csv_rows()
    return summarize([",".join(r) for r in rows])


def summarize(lines):
    by_sensor = {}
    for line in lines:
        _, sensor, value, _ = line.split(",")
        count, total = by_sensor.get(sensor, (0, 0))
        by_sensor[sensor] = (count + 1, total + int(value))
    return {"messages": len(lines), "valueMilliSum": sum(t for _, t in by_sensor.values()),
            "bySensor": {k: {"count": c, "valueMilliSum": t} for k, (c, t) in sorted(by_sensor.items())}}


def bookie_ledgers():
    return {int(k) for k in (call("GET", f"{BOOKIE}/api/v1/ledger/list/") or {})}


def s3_objects():
    root = ET.fromstring(call("GET", f"{S3}/{BUCKET}?list-type=2&max-keys=1000", raw=True))
    ns = {"s": root.tag[1:].split("}")[0]} if root.tag.startswith("{") else {}
    prefix = "s:" if ns else ""
    out = []
    for c in root.findall(f"{prefix}Contents", ns):
        key = c.find(f"{prefix}Key", ns).text
        m = re.search(r"-ledger-(\d+)(-index)?$", key)
        out.append({"key": key, "size": int(c.find(f"{prefix}Size", ns).text),
                    "ledgerId": int(m.group(1)) if m else None, "kind": "index" if m and m.group(2) else "data"})
    return out


def internal_stats():
    try:
        return admin("GET", f"{TOPIC_PATH}/internalStats")
    except HttpError as e:
        if e.code == 404:
            return None
        raise


def topic_view():
    stats = internal_stats()
    in_bookie = bookie_ledgers()
    objects = s3_objects()
    if stats is None:
        return {"exists": False, "ledgers": [], "objects": objects, "bookieLedgers": sorted(in_bookie)}
    ledgers = []
    raw = stats.get("ledgers", [])
    for i, l in enumerate(raw):
        lid = l["ledgerId"]
        current = i == len(raw) - 1
        entries = stats.get("currentLedgerEntries", 0) if current else l.get("entries", 0)
        ledgers.append({"ledgerId": lid, "entries": entries, "size": stats.get("currentLedgerSize", 0) if current else l.get("size", 0),
                        "offloaded": bool(l.get("offloaded")), "open": current, "inBookie": lid in in_bookie,
                        "s3Objects": [o["key"] for o in objects if o["ledgerId"] == lid]})
    mine = {l["ledgerId"] for l in ledgers}
    return {"exists": True, "topic": TOPIC, "entriesAddedCounter": stats.get("entriesAddedCounter"),
            "numberOfEntries": stats.get("numberOfEntries"), "totalSize": stats.get("totalSize"),
            "lastConfirmedEntry": stats.get("lastConfirmedEntry"), "state": stats.get("state"),
            "ledgers": ledgers, "objects": [o for o in objects if o["ledgerId"] in mine],
            "otherObjects": len([o for o in objects if o["ledgerId"] not in mine]), "bookieLedgers": sorted(in_bookie)}


def cluster_view():
    brokers = call("GET", f"{ADMIN}/admin/v2/brokers/{CLUSTER}")
    bookies = admin("GET", "bookies/all").get("bookies", [])
    try:
        owner = call("GET", f"{ADMIN}/lookup/v2/topic/{TOPIC_PATH}")
    except HttpError:
        owner = None
    info = call("GET", f"{BOOKIE}/api/v1/bookie/info")
    runtime = admin("GET", "brokers/configuration/runtime")
    return {"cluster": CLUSTER, "brokers": brokers, "bookies": bookies, "topicOwner": owner, "bookieInfo": info,
            "bookieLedgers": sorted(bookie_ledgers()), "bucket": BUCKET, "s3Endpoint": S3,
            "brokerConfig": {k: runtime.get(k) for k in BROKER_KEYS}}


def publish():
    lines = [",".join(r) for r in csv_rows()]
    producer = CLIENT.create_producer(TOPIC, batching_enabled=False, block_if_queue_full=True)
    started = time.time()
    ids = []
    try:
        for line in lines:
            ids.append(producer.send(line.encode()))
    finally:
        producer.close()
    ledgers = {}
    for mid in ids:
        ledgers[mid.ledger_id()] = ledgers.get(mid.ledger_id(), 0) + 1
    return {"published": len(ids), "ms": round((time.time() - started) * 1000, 1), "perLedger": ledgers}


def offload():
    last = admin("GET", f"{TOPIC_PATH}/lastMessageId")
    admin("PUT", f"{TOPIC_PATH}/offload", {"ledgerId": last["ledgerId"], "entryId": last["entryId"], "partitionIndex": -1})
    return {"requestedUpTo": {"ledgerId": last["ledgerId"], "entryId": last["entryId"]}, **offload_status()}


def offload_status():
    try:
        return admin("GET", f"{TOPIC_PATH}/offload")
    except HttpError as e:
        return {"status": "NOT_RUN", "lastError": e.args[0][:200]}


def read_back():
    stats = internal_stats()
    offloaded = {l["ledgerId"] for l in (stats or {}).get("ledgers", []) if l.get("offloaded")}
    in_bookie = bookie_ledgers()
    reader = CLIENT.create_reader(TOPIC, pulsar.MessageId.earliest)
    started = time.time()
    lines, per_ledger = [], {}
    try:
        while reader.has_message_available():
            msg = reader.read_next(timeout_millis=30000)
            lid = msg.message_id().ledger_id()
            lines.append(msg.data().decode())
            per_ledger[lid] = per_ledger.get(lid, 0) + 1
    finally:
        reader.close()
    source = [{"ledgerId": lid, "messages": n, "servedFrom": "tiered storage (MinIO)" if lid in offloaded and lid not in in_bookie
               else "BookKeeper" + (" (also offloaded)" if lid in offloaded else "")} for lid, n in sorted(per_ledger.items())]
    return {"ms": round((time.time() - started) * 1000, 1), "read": summarize(lines), "expected": expected(),
            "matches": lines == [",".join(r) for r in csv_rows()], "ledgers": source, "first": lines[:3], "last": lines[-3:]}


def object_peek(key):
    if not any(o["key"] == key for o in s3_objects()):
        raise HttpError(404, "no such object")
    blob = call("GET", f"{S3}/{BUCKET}/{key}", raw=True)
    found = sorted((line for line in (",".join(r) for r in csv_rows()) if line.encode() in blob), key=lambda line: blob.find(line.encode()))
    return {"key": key, "bytes": len(blob), "csvLinesInside": len(found), "firstLines": found[:5], "lastLines": found[-3:]}


def reset():
    try:
        admin("DELETE", f"{TOPIC_PATH}?force=true")
    except HttpError as e:
        if e.code != 404:
            raise
    return {"deleted": TOPIC}


ROUTES = {
    ("GET", "/api/cluster"): lambda q: cluster_view(),
    ("GET", "/api/topic"): lambda q: topic_view(),
    ("GET", "/api/expected"): lambda q: expected(),
    ("GET", "/api/offload"): lambda q: offload_status(),
    ("GET", "/api/read"): lambda q: read_back(),
    ("GET", "/api/object"): lambda q: object_peek(q.get("key", [""])[0]),
    ("POST", "/api/publish"): lambda q: publish(),
    ("POST", "/api/offload"): lambda q: offload(),
    ("POST", "/api/reset"): lambda q: reset(),
}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, kind="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_method(self, method):
        url = urlparse(self.path)
        if method == "GET" and url.path in ("/", "/index.html"):
            return self.send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
        route = ROUTES.get((method, url.path))
        if route is None:
            return self.send(404, {"error": f"no route {method} {url.path}"})
        try:
            if method == "POST":
                with LOCK:
                    result = route(parse_qs(url.query))
            else:
                result = route(parse_qs(url.query))
            self.send(200, result)
        except HttpError as e:
            self.send(e.code if 400 <= e.code < 500 else 502, {"error": str(e)[:500]})
        except Exception as e:
            self.send(500, {"error": f"{type(e).__name__}: {e}"[:500]})

    def do_GET(self):
        self.handle_method("GET")

    def do_POST(self):
        self.handle_method("POST")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"ui on :{PORT}, broker {ADMIN}, bookie {BOOKIE}, s3 {S3}/{BUCKET}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
