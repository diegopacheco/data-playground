import json
import os
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import catalog
import pipeline
from openmetadata import OpenMetadata

APP = Path(__file__).resolve().parent
OM = OpenMetadata()
LOCK = threading.Lock()
STATE = {"lastIngest": None}


def status():
    version = OM.raw("GET", "/system/version", auth=False)
    service = OM.find("/services/databaseServices/name/" + pipeline.CURATION["service"])
    tables = catalog.catalog(OM) if service else []
    return {"openmetadata": version["version"], "openmetadataUrl": catalog.PUBLIC_URL, "service": pipeline.CURATION["service"],
            "serviceExists": service is not None, "tables": len(tables), "lastIngest": STATE["lastIngest"]}


def ingest():
    if not LOCK.acquire(blocking=False):
        return 409, {"ok": False, "error": "ingestion already running"}
    try:
        STATE["lastIngest"] = pipeline.run(OM)
        return 200, STATE["lastIngest"]
    except Exception as e:
        STATE["lastIngest"] = {"ok": False, "error": str(e), "trace": traceback.format_exc()[-2000:]}
        return 500, STATE["lastIngest"]
    finally:
        LOCK.release()


def search(q):
    hits = OM.search(q)["hits"]["hits"]
    return {"q": q, "hits": [{"key": catalog.short(h["_source"]["fullyQualifiedName"]), "fqn": h["_source"]["fullyQualifiedName"],
                              "description": h["_source"].get("description"), "tags": catalog.tags_of(h["_source"]), "score": h.get("_score")} for h in hits]}


def vocabulary():
    c, g = pipeline.CURATION["classification"]["name"], pipeline.CURATION["glossary"]["name"]
    return {
        "tags": [{"fqn": t["fullyQualifiedName"], "description": t.get("description")} for t in OM.get("/tags", parent=c, limit=100)["data"]],
        "terms": [{"fqn": t["fullyQualifiedName"], "displayName": t.get("displayName"), "description": t.get("description")} for t in OM.get("/glossaryTerms", glossary=OM.get("/glossaries/name/" + g)["id"], limit=100)["data"]],
        "teams": [{"name": t["name"], "displayName": t.get("displayName")} for t in (OM.find("/teams/name/" + x["name"]) for x in pipeline.CURATION["teams"]) if t],
        "users": [{"name": u["name"], "displayName": u.get("displayName")} for u in (OM.find("/users/name/" + x["name"]) for x in pipeline.CURATION["users"]) if u],
    }


def lineage():
    tables = catalog.catalog(OM)
    return {"nodes": [{"key": t["key"], "type": t["type"]} for t in tables], "edges": catalog.lineage(OM, tables)}


ROUTES = {
    "/api/status": status,
    "/api/catalog": lambda: {"tables": catalog.catalog(OM)},
    "/api/lineage": lineage,
    "/api/verify": lambda: catalog.verify(OM),
    "/api/vocabulary": vocabulary,
}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, code, payload):
        self.send(code, json.dumps(payload).encode(), "application/json")

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        try:
            if url.path == "/":
                self.send(200, (APP / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/search":
                self.send_json(200, search(urllib.parse.parse_qs(url.query).get("q", ["*"])[0]))
            elif url.path in ROUTES:
                self.send_json(200, ROUTES[url.path]())
            else:
                self.send_json(404, {"error": "not found"})
        except Exception as e:
            self.send_json(502, {"error": str(e)})

    def do_POST(self):
        if self.path == "/api/ingest":
            self.send_json(*ingest())
        else:
            self.send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("UI_PORT", "8080"))
    print(f"ui listening on {port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
