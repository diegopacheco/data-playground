import json
import subprocess
import sys
import time
from pathlib import Path
from openmetadata import OM_URL
from source import PG

CURATION = json.loads((Path(__file__).resolve().parent / "curation.json").read_text())


def fqn(name):
    return f"{CURATION['service']}.{CURATION['database']}.{name}"


def workflow_config(source_type, source_config, token):
    return {
        "source": {
            "type": source_type,
            "serviceName": CURATION["service"],
            "serviceConnection": {"config": {
                "type": "Postgres",
                "username": PG["user"],
                "authType": {"password": PG["password"]},
                "hostPort": f"{PG['host']}:{PG['port']}",
                "database": PG["dbname"],
                "ingestAllDatabases": False,
            }},
            "sourceConfig": {"config": {**source_config, "schemaFilterPattern": {"includes": [f"^{s}$" for s in CURATION["schemas"]]}}},
        },
        "sink": {"type": "metadata-rest", "config": {}},
        "workflowConfig": {
            "loggerLevel": "WARN",
            "openMetadataServerConfig": {"hostPort": OM_URL + "/api", "authProvider": "openmetadata", "securityConfig": {"jwtToken": token}},
        },
    }


def run_workflow(config):
    done = subprocess.run([sys.executable, __file__], input=json.dumps(config), capture_output=True, text=True, timeout=600)
    if done.returncode != 0:
        raise RuntimeError(f"{config['source']['type']} workflow failed: {done.stderr.strip()[-1500:]}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def execute_workflow(config):
    from metadata.workflow.metadata import MetadataWorkflow
    workflow = MetadataWorkflow.create(config)
    workflow.execute()
    try:
        workflow.raise_from_status()
        steps = [{"name": s.name, "records": len(s.status.records), "warnings": len(s.status.warnings), "failures": len(s.status.failures)} for s in workflow.workflow_steps()]
    finally:
        workflow.stop()
    return steps


def label(tag):
    source = "Glossary" if tag.split(".")[0] == CURATION["glossary"]["name"] else "Classification"
    return {"tagFQN": tag, "source": source, "labelType": "Manual", "state": "Confirmed"}


def ensure_people(om):
    teams = {}
    for team in CURATION["teams"]:
        teams[team["name"]] = om.put("/teams", {**team, "teamType": "Group"})["id"]
    users = {}
    for user in CURATION["users"]:
        found = om.find("/users/name/" + user["name"])
        body = {"name": user["name"], "displayName": user["displayName"], "email": user["email"], "teams": [teams[user["team"]]]}
        users[user["name"]] = found["id"] if found else om.post("/users", body)["id"]
    return {"team": teams, "user": users}


def ensure_vocabulary(om):
    c = CURATION["classification"]
    om.put("/classifications", {"name": c["name"], "description": c["description"]})
    for tag in c["tags"]:
        om.put("/tags", {**tag, "classification": c["name"]})
    g = CURATION["glossary"]
    om.put("/glossaries", {"name": g["name"], "displayName": g["displayName"], "description": g["description"]})
    for term in g["terms"]:
        om.put("/glossaryTerms", {**term, "glossary": g["name"]})


def curate_tables(om, people):
    for name, spec in CURATION["tables"].items():
        table = om.table(fqn(name), fields="columns")
        index = {c["name"]: i for i, c in enumerate(table["columns"])}
        ops = [
            {"op": "add", "path": "/tags", "value": [label(t) for t in spec["tags"]]},
            {"op": "add", "path": "/owners", "value": [{"id": people[o["type"]][o["name"]], "type": o["type"]} for o in spec["owners"]]},
        ]
        for column, tags in spec["columns"].items():
            ops.append({"op": "add", "path": f"/columns/{index[column]}/tags", "value": [label(t) for t in tags]})
        om.patch(f"/tables/{table['id']}", ops)


def add_lineage(om):
    for edge in CURATION["lineage"]:
        source, target = om.table(fqn(edge["from"]), fields=""), om.table(fqn(edge["to"]), fields="")
        om.put("/lineage", {"edge": {
            "fromEntity": {"id": source["id"], "type": "table"},
            "toEntity": {"id": target["id"], "type": "table"},
            "lineageDetails": {"sqlQuery": edge["sql"], "description": edge["description"], "source": "Manual"},
        }})


def search_ready(om):
    hits = om.search(f"service.name:{CURATION['service']}", size=50)["hits"]["hits"]
    docs = {h["_source"]["fullyQualifiedName"]: h["_source"] for h in hits}
    for name, spec in CURATION["tables"].items():
        doc = docs.get(fqn(name))
        if doc is None:
            return False
        indexed = {t["tagFQN"] for t in doc.get("tags") or []} | {(doc.get("tier") or {}).get("tagFQN")}
        if not set(spec["tags"]) <= indexed:
            return False
    return True


def reindex(om):
    started = int(time.time() * 1000) - 2000
    om.post("/apps/trigger/SearchIndexingApplication", {})
    for _ in range(60):
        time.sleep(1)
        runs = [r for r in om.get("/apps/name/SearchIndexingApplication/status", offset=0, limit=1)["data"] if r.get("startTime", 0) >= started]
        if runs and runs[0].get("status") in ("success", "completed"):
            return
        if runs and runs[0].get("status") in ("failed", "activeError"):
            raise RuntimeError(f"search reindex {runs[0]['status']}")
    raise RuntimeError("search reindex did not finish after 60 tries")


def wait_search(om):
    for attempt in range(15):
        if search_ready(om):
            return {"attempts": attempt + 1, "reindexed": False}
        time.sleep(1)
    reindex(om)
    for attempt in range(30):
        if search_ready(om):
            return {"attempts": attempt + 16, "reindexed": True}
        time.sleep(1)
    raise RuntimeError("search index does not show the curated tags even after a full reindex")


def run(om):
    report, started = [], time.time()

    def step(name, fn):
        t = time.time()
        detail = fn()
        report.append({"step": name, "seconds": round(time.time() - t, 2), "detail": detail})

    token = om.bot_token()
    step("metadata ingestion (tables, views, columns, comments)", lambda: run_workflow(workflow_config("postgres", {"type": "DatabaseMetadata", "includeTables": True, "includeViews": True, "includeTags": False, "markDeletedTables": True, "overrideMetadata": True}, token)))
    step("lineage ingestion (view definitions)", lambda: run_workflow(workflow_config("postgres-lineage", {"type": "DatabaseLineage", "processViewLineage": True, "processQueryLineage": False, "processStoredProcedureLineage": False}, token)))
    people = {}
    step("teams and users", lambda: people.update(ensure_people(om)) or {k: len(v) for k, v in people.items()})
    step("classification and glossary", lambda: ensure_vocabulary(om) or {"tags": len(CURATION["classification"]["tags"]), "terms": len(CURATION["glossary"]["terms"])})
    step("tags, glossary terms and owners on tables", lambda: curate_tables(om, people) or {"tables": len(CURATION["tables"])})
    step("manual lineage edges", lambda: add_lineage(om) or {"edges": len(CURATION["lineage"])})
    step("search index caught up", lambda: wait_search(om))
    return {"ok": True, "seconds": round(time.time() - started, 2), "steps": report}


if __name__ == "__main__":
    print(json.dumps(execute_workflow(json.loads(sys.stdin.read()))))
