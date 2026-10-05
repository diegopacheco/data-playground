import json
import os
import shutil

import duckdb
from dbt.cli.main import dbtRunner

from workspace import (
    BREAKING,
    NON_BREAKING,
    RESULTS,
    apply_breaking,
    apply_non_breaking,
    fresh,
    read_results,
    timed,
)

PROJECT = fresh("dbt")
os.chdir(PROJECT)
STATE = PROJECT / "state"
RUNNER = dbtRunner()


def invoke(*args):
    res = RUNNER.invoke([*args, "--project-dir", str(PROJECT), "--profiles-dir", str(PROJECT)])
    if not res.success:
        raise RuntimeError(f"dbt {' '.join(args)} failed: {res.exception}")
    return res.result.results


def summarize(results):
    built = [r for r in results if str(r.node.resource_type) in ("model", "seed") and str(r.status) == "success"]
    tests = [r for r in results if str(r.node.resource_type) == "test"]
    return {
        "models_rebuilt": sorted(r.node.name for r in built),
        "tests": len(tests),
        "tests_passed": sum(1 for r in tests if str(r.status) == "pass"),
    }


def step(*args):
    results, seconds = timed(lambda: invoke(*args))
    info = summarize(results)
    info.update({"seconds": seconds, "command": "dbt " + " ".join(args)})
    return info


def incremental_rows():
    con = duckdb.connect(str(PROJECT / "warehouse.duckdb"))
    pending = con.execute("SELECT count(*) FROM sales.stg_orders WHERE ts > (SELECT max(ts) FROM sales.fct_orders)").fetchone()[0]
    total = con.execute("SELECT count(*) FROM sales.fct_orders").fetchone()[0]
    con.close()
    return {"pending": pending, "total": total}


def save_state():
    STATE.mkdir(exist_ok=True)
    shutil.copy(PROJECT / "target" / "manifest.json", STATE / "manifest.json")


def node_lineage():
    manifest = json.loads((PROJECT / "target" / "manifest.json").read_text())
    edges = []
    for child, parents in manifest["parent_map"].items():
        if child.startswith("model."):
            for parent in parents:
                edges.append({"from": parent.split(".")[-1], "to": child.split(".")[-1]})
    return sorted(edges, key=lambda e: (e["to"], e["from"]))


def fetch():
    con = duckdb.connect(str(PROJECT / "warehouse.duckdb"))
    results = read_results(con)
    dev_columns = [r[0] for r in con.execute("DESCRIBE sales_dev.stg_orders").fetchall()]
    con.close()
    return results, dev_columns


def main():
    steps = {}
    steps["initial_build"] = step("build")
    steps["test"] = step("test")
    before = incremental_rows()
    steps["incremental_run_no_new_rows"] = step("run", "--select", "fct_orders")
    steps["incremental_run_no_new_rows"].update(
        {
            "rows_matching_incremental_filter": before["pending"],
            "fct_orders_rows_before": before["total"],
            "fct_orders_rows_after": incremental_rows()["total"],
        }
    )
    steps["scheduled_build"] = step("build")
    steps["full_refresh_fct_and_children"] = step("build", "--select", "fct_orders+", "--full-refresh")
    save_state()
    steps["state_modified_no_change"] = step("build", "--select", "state:modified+", "--state", "state")
    steps["dev_env_no_change"] = step("build", "--target", "dev")
    steps["dev_env_defer_no_change"] = step("build", "--target", "dev", "--select", "state:modified+", "--defer", "--state", "state")
    apply_non_breaking(PROJECT)
    steps["non_breaking_change_dev"] = step("build", "--target", "dev", "--select", "state:modified+", "--state", "state")
    steps["promote_non_breaking_prod"] = step("build", "--select", "state:modified+", "--state", "state")
    save_state()
    apply_breaking(PROJECT)
    steps["breaking_change_dev"] = step("build", "--target", "dev", "--select", "state:modified+", "--state", "state")
    lineage = node_lineage()
    results, dev_columns = fetch()
    report = {
        "tool": "dbt",
        "changes": {"non_breaking": NON_BREAKING, "breaking": BREAKING},
        "steps": steps,
        "node_lineage": lineage,
        "dev_stg_orders_columns": dev_columns,
        "results": results,
    }
    (RESULTS / "dbt.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: {"seconds": v["seconds"], "models_rebuilt": v["models_rebuilt"]} for k, v in steps.items()}, indent=1))


if __name__ == "__main__":
    main()
