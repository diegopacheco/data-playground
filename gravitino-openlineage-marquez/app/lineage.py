import json
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from gravitino import GRAVITINO_URL, load_table
from model import METALAKE, JOB_NAMESPACE, full_name

PRODUCER = "urn:gravitino-openlineage-marquez:pipeline:1.0"
SPEC = "https://openlineage.io/spec"
EVENT_SCHEMA = f"{SPEC}/2-0-2/OpenLineage.json#/$defs/RunEvent"


def facet(name, version, **fields):
    return {"_producer": PRODUCER, "_schemaURL": f"{SPEC}/facets/{version}/{name}.json#/$defs/{name}", **fields}


def now():
    return datetime.now(timezone.utc).isoformat()


def file_dataset(path, header):
    return {"namespace": "file", "name": path, "facets": {
        "schema": facet("SchemaDatasetFacet", "1-1-1", fields=[{"name": h, "type": "string"} for h in header]),
    }}


def table_dataset(t):
    registered = load_table(t["schema"], t["name"])
    return {"namespace": METALAKE, "name": full_name(t), "facets": {
        "schema": facet("SchemaDatasetFacet", "1-1-1", fields=[
            {"name": c["name"], "type": c["type"], "description": c.get("comment", "")} for c in registered["columns"]]),
        "documentation": facet("DocumentationDatasetFacet", "1-0-1", description=registered.get("comment", "")),
        "ownership": facet("OwnershipDatasetFacet", "1-0-1", owners=[{"name": f"group:{t['owner']}", "type": "GROUP"}]),
    }}


def job(name, description, sql):
    return {"namespace": JOB_NAMESPACE, "name": name, "facets": {
        "jobType": facet("JobTypeJobFacet", "2-0-3", processingType="BATCH", integration="PYTHON", jobType="JOB"),
        "documentation": facet("DocumentationJobFacet", "1-0-1", description=description),
        "sql": facet("SQLJobFacet", "1-1-0", query=sql),
    }}


def event(event_type, run_id, job_, inputs, outputs, run_facets=None):
    return {"eventType": event_type, "eventTime": now(), "producer": PRODUCER, "schemaURL": EVENT_SCHEMA,
            "run": {"runId": str(run_id), "facets": run_facets or {}}, "job": job_, "inputs": inputs, "outputs": outputs}


def with_row_count(dataset, rows):
    return {**dataset, "outputFacets": {"outputStatistics": facet("OutputStatisticsOutputDatasetFacet", "1-0-2", rowCount=rows)}}


def error_facet(error):
    return {"errorMessage": facet("ErrorMessageRunFacet", "1-0-1", message=str(error), programmingLanguage="PYTHON")}


def emit(ev):
    request = Request(f"{GRAVITINO_URL}/api/lineage", data=json.dumps(ev).encode(), method="POST",
                      headers={"Accept": "application/json", "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.status
    except HTTPError as e:
        raise RuntimeError(f"gravitino /api/lineage rejected {ev['eventType']} with {e.code}: {e.read().decode()}") from e
