import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import dlt
import duckdb
from dlt.sources.rest_api import rest_api_resources
from dlt.sources.sql_database import sql_table

import source_db

STATE = Path(os.environ.get("STATE_DIR", Path(__file__).resolve().parent.parent / ".run" / "state"))
DB_FILE = STATE / "shop.duckdb"
PIPELINES_DIR = STATE / "pipelines"
RUNS_FILE = STATE / "runs.json"
API_URL = os.environ.get("API_URL", "http://localhost:8080/source/")
PIPELINE = "shop"
DATASET = "ingest"


@dlt.source(name="shop")
def shop():
    orders = sql_table(
        credentials=source_db.DSN.replace("postgresql://", "postgresql+psycopg2://", 1),
        table="orders",
        incremental=dlt.sources.incremental("updated_at"),
        write_disposition="merge",
        primary_key="order_id",
    )
    orders.apply_hints(columns={"deleted": {"name": "deleted", "hard_delete": True}})
    yield orders
    yield from rest_api_resources({
        "client": {"base_url": API_URL},
        "resource_defaults": {"write_disposition": "merge", "primary_key": "id"},
        "resources": [{
            "name": "customers",
            "endpoint": {
                "path": "customers",
                "data_selector": "data",
                "params": {
                    "page_size": 5,
                    "updated_since": {
                        "type": "incremental",
                        "cursor_path": "updated_at",
                        "initial_value": "1970-01-01T00:00:00+00:00",
                    },
                },
                "paginator": {"type": "page_number", "page_param": "page", "base_page": 1, "total_path": "pages"},
            },
        }],
    })


def pipeline():
    STATE.mkdir(parents=True, exist_ok=True)
    return dlt.pipeline(
        pipeline_name=PIPELINE,
        destination=dlt.destinations.duckdb(str(DB_FILE)),
        dataset_name=DATASET,
        pipelines_dir=str(PIPELINES_DIR),
    )


def user_columns(schema):
    return {
        name: sorted(table.get("columns", {}))
        for name, table in schema.get("tables", {}).items()
        if not name.startswith("_dlt")
    }


def added_columns(before, after):
    added = []
    for table, columns in after.items():
        for column in columns:
            if column not in before.get(table, []):
                added.append(f"{table}.{column}")
    return added


def load_runs():
    return json.loads(RUNS_FILE.read_text()) if RUNS_FILE.exists() else []


def run():
    p = pipeline()
    before = user_columns(p.default_schema.to_dict()) if p.default_schema_name else {}
    started = time.perf_counter()
    info = p.run(shop())
    duration = time.perf_counter() - started
    after = user_columns(p.default_schema.to_dict())
    counts = p.last_trace.last_normalize_info.row_counts if p.last_trace.last_normalize_info else {}
    record = {
        "run": len(load_runs()) + 1,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "duration_ms": round(duration * 1000, 1),
        "load_ids": list(info.loads_ids),
        "row_counts": {t: n for t, n in counts.items() if not t.startswith("_dlt")},
        "schema_version": p.default_schema.version,
        "schema_hash": p.default_schema.version_hash,
        "new_columns": [] if not before else added_columns(before, after),
        "failed_jobs": info.has_failed_jobs,
    }
    RUNS_FILE.write_text(json.dumps(load_runs() + [record], indent=1))
    return record


def reset():
    shutil.rmtree(STATE, ignore_errors=True)
    STATE.mkdir(parents=True, exist_ok=True)


def sql(statement, params=None):
    if not DB_FILE.exists():
        return {"columns": [], "rows": []}
    with duckdb.connect(str(DB_FILE)) as con:
        cur = con.execute(statement, params or [])
        columns = [d[0] for d in cur.description] if cur.description else []
        return {"columns": columns, "rows": [list(r) for r in cur.fetchall()]}


def tables():
    names = sql(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = ? ORDER BY table_name", [DATASET]
    )["rows"]
    return [
        {"table": n, "rows": sql(f'SELECT count(*) FROM {DATASET}."{n}"')["rows"][0][0]}
        for (n,) in names
    ]


def loads():
    if not DB_FILE.exists():
        return []
    result = sql(
        f"SELECT load_id, schema_name, status, inserted_at, schema_version_hash FROM {DATASET}._dlt_loads ORDER BY inserted_at"
    )
    return [dict(zip(result["columns"], r)) for r in result["rows"]]


def versions():
    if not DB_FILE.exists():
        return []
    rows = sql(f"SELECT version, version_hash, inserted_at, schema FROM {DATASET}._dlt_version ORDER BY version")["rows"]
    history = []
    previous = {}
    for version, version_hash, inserted_at, schema in rows:
        columns = user_columns(json.loads(schema))
        history.append({
            "version": version,
            "version_hash": version_hash,
            "inserted_at": inserted_at,
            "tables": sorted(columns),
            "added_columns": added_columns(previous, columns),
        })
        previous = columns
    return history


COLUMN_HINTS = ["primary_key", "hard_delete", "nullable", "incremental", "unique", "row_key", "parent_key", "root_key"]


def schema():
    p = pipeline()
    if not p.default_schema_name:
        return {"name": None, "version": None, "tables": []}
    s = p.default_schema.to_dict()
    result = []
    for name, table in s["tables"].items():
        if name.startswith("_dlt"):
            continue
        result.append({
            "table": name,
            "parent": table.get("parent"),
            "write_disposition": table.get("write_disposition") or s["tables"].get(table.get("parent") or "", {}).get("write_disposition"),
            "columns": [
                {"name": c, "data_type": v.get("data_type"), "hints": [h for h in COLUMN_HINTS if v.get(h) and h != "nullable"] + ([] if v.get("nullable", True) else ["not null"])}
                for c, v in table.get("columns", {}).items()
            ],
        })
    return {"name": s["name"], "version": s["version"], "version_hash": s["version_hash"], "tables": result}
