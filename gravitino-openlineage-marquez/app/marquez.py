import json
import os
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from model import METALAKE, JOB_NAMESPACE, CATALOG

MARQUEZ_URL = os.environ.get("MARQUEZ_URL", "http://localhost:27101")
ROOT_NODE = f"dataset:{METALAKE}:{CATALOG}.gold.revenue_by_category"


def call(path, missing_ok=False):
    request = Request(f"{MARQUEZ_URL}/api/v1{path}", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as e:
        if missing_ok and e.code == 404:
            return None
        raise RuntimeError(f"marquez GET {path} failed with {e.code}: {e.read().decode()}") from e


def run(run_id):
    return call(f"/jobs/runs/{run_id}", missing_ok=True)


def wait_for_runs(run_ids, tries=60):
    for _ in range(tries):
        states = {r: (run(r) or {}).get("state") for r in run_ids}
        if all(s == "COMPLETED" for s in states.values()):
            return states
        time.sleep(1)
    raise RuntimeError(f"marquez did not record every run as COMPLETED: {states}")


def datasets(namespace=METALAKE):
    found = call(f"/namespaces/{quote(namespace)}/datasets?limit=100", missing_ok=True)
    return found["datasets"] if found else []


def jobs(namespace=JOB_NAMESPACE):
    found = call(f"/namespaces/{quote(namespace)}/jobs?limit=100", missing_ok=True)
    return found["jobs"] if found else []


def runs(job, namespace=JOB_NAMESPACE, limit=20):
    return call(f"/namespaces/{quote(namespace)}/jobs/{quote(job)}/runs?limit={limit}")["runs"]


def row_count(r):
    for version in r.get("outputDatasetVersions", []):
        stats = version.get("facets", {}).get("outputStatistics")
        if stats:
            return stats.get("rowCount")
    return None


def run_view(r):
    return {"id": r["id"], "state": r["state"], "started": r.get("startedAt"), "ended": r.get("endedAt"),
            "duration_ms": r.get("durationMs"), "rows": row_count(r),
            "outputs": [v["datasetVersionId"]["name"] for v in r.get("outputDatasetVersions", [])]}


def pipeline_runs():
    return sorted(job_views(), key=lambda j: min((r["started"] or "") for r in j["runs"]) if j["runs"] else "")


def job_views():
    return [{"job": j["name"], "namespace": j["namespace"], "type": j.get("type"), "description": j.get("description"),
             "inputs": [d["name"] for d in j.get("inputs", [])], "outputs": [d["name"] for d in j.get("outputs", [])],
             "sql": (j.get("facets", {}).get("sql") or {}).get("query"),
             "runs": [run_view(r) for r in runs(j["name"])]} for j in jobs()]


def graph(node_id=ROOT_NODE, depth=20):
    found = call(f"/lineage?{urlencode({'nodeId': node_id, 'depth': depth})}", missing_ok=True)
    if not found:
        return {"nodes": [], "edges": [], "dataset_edges": []}
    nodes = [{"id": n["id"], "type": n["type"], "namespace": n["data"].get("namespace"), "name": n["data"].get("name")}
             for n in found["graph"]]
    edges = sorted({(e["origin"], e["destination"]) for n in found["graph"] for e in n["outEdges"]})
    dataset_edges = sorted({(i, o) for n in found["graph"] if n["type"] == "JOB"
                            for i in (e["origin"] for e in n["inEdges"]) for o in (e["destination"] for e in n["outEdges"])})
    return {"root": node_id, "nodes": nodes, "edges": [list(e) for e in edges], "dataset_edges": [list(e) for e in dataset_edges]}
