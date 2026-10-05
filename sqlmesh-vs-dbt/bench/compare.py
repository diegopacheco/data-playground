import json
import platform
import subprocess
from importlib.metadata import version

from workspace import RESULTS, ROOT

SCENARIOS = [
    ("Initial build (seed + 4 models)", "initial_build", "initial_build"),
    ("Run tests / audits", "audit", "test"),
    ("Incremental run, no new data", "run_no_new_intervals", "incremental_run_no_new_rows"),
    ("Next scheduled daily run", "run_next_interval", "scheduled_build"),
    ("Reprocess 2026-01-10..11 of fct_orders", "restate_two_days", "full_refresh_fct_and_children"),
    ("Create dev environment, no change", "dev_env_no_change", "dev_env_no_change"),
    ("Dev environment with --defer (slim)", None, "dev_env_defer_no_change"),
    ("Unchanged project vs prod state", "plan_no_change_prod", "state_modified_no_change"),
    ("Non-breaking change in dev", "non_breaking_change_dev", "non_breaking_change_dev"),
    ("Promote non-breaking change to prod", "promote_non_breaking_prod", "promote_non_breaking_prod"),
    ("Breaking change in dev", "breaking_change_dev", "breaking_change_dev"),
]

FEATURES = [
    ("Change classification", "Automatic per plan: BREAKING / NON_BREAKING / INDIRECT_*", "None: state:modified marks the node and everything downstream"),
    ("Environments", "Virtual: dev is a set of views over versioned physical tables, promotion is a view swap", "Physical: every target schema is rebuilt, --defer only reads prod relations"),
    ("Incremental semantics", "INCREMENTAL_BY_TIME_RANGE with tracked intervals, restate any date range", "is_incremental() filter written by hand (max(ts)), reprocess needs --full-refresh"),
    ("Column-level lineage", "Built in, parsed with sqlglot", "Not in dbt-core (node level from manifest.json)"),
    ("Data quality", "Audits run on every backfill (blocking)", "Data tests run by dbt test / dbt build"),
    ("Change selection", "Computed from model fingerprints in the state DB", "state:modified+ against a saved manifest.json"),
]


def load(name):
    return json.loads((RESULTS / f"{name}.json").read_text())


def cell(steps, key):
    if key is None:
        return None
    s = steps[key]
    return {
        "seconds": s["seconds"],
        "models_rebuilt": len(s["models_rebuilt"]),
        "models": s["models_rebuilt"],
        "command": s["command"],
        "detail": {k: v for k, v in s.items() if k not in ("seconds", "models_rebuilt", "command", "environment")},
    }


def awk_rows():
    out = subprocess.run(["bash", str(ROOT / "bench" / "awk_revenue_by_category.sh")], check=True, capture_output=True, text=True).stdout
    rows = []
    for line in out.strip().splitlines():
        category, orders, quantity, revenue = line.split(",")
        rows.append({"category": category, "total_orders": int(orders), "total_quantity": int(quantity), "total_revenue": float(revenue)})
    return rows


def main():
    sq, db = load("sqlmesh"), load("dbt")
    awk = awk_rows()
    identical = sq["results"] == db["results"]
    awk_match = awk == sq["results"]["revenue_by_category"] == db["results"]["revenue_by_category"]
    non_breaking = {
        "sqlmesh": len(sq["steps"]["non_breaking_change_dev"]["models_rebuilt"]) + len(sq["steps"]["promote_non_breaking_prod"]["models_rebuilt"]),
        "dbt": len(db["steps"]["non_breaking_change_dev"]["models_rebuilt"]) + len(db["steps"]["promote_non_breaking_prod"]["models_rebuilt"]),
    }
    comparison = {
        "versions": {
            "python": platform.python_version(),
            "sqlmesh": version("sqlmesh"),
            "dbt-core": version("dbt-core"),
            "dbt-duckdb": version("dbt-duckdb"),
            "duckdb": version("duckdb"),
        },
        "changes": sq["changes"],
        "scenarios": [
            {"scenario": title, "sqlmesh": cell(sq["steps"], s_key), "dbt": cell(db["steps"], d_key)}
            for title, s_key, d_key in SCENARIOS
        ],
        "small_change_models_rebuilt_dev_plus_prod": non_breaking,
        "classification": {
            "non_breaking": sq["steps"]["non_breaking_change_dev"]["changes"],
            "breaking": sq["steps"]["breaking_change_dev"]["changes"],
        },
        "features": [{"feature": f, "sqlmesh": s, "dbt": d} for f, s, d in FEATURES],
        "lineage": {"sqlmesh_columns": sq["column_lineage"], "dbt_nodes": db["node_lineage"]},
        "dev_stg_orders_columns": {"sqlmesh": sq["dev_stg_orders_columns"], "dbt": db["dev_stg_orders_columns"]},
        "results": {"sqlmesh": sq["results"], "dbt": db["results"], "awk_revenue_by_category": awk},
        "checks": {"results_identical": identical, "revenue_by_category_matches_awk": awk_match},
    }
    (ROOT / "comparison.json").write_text(json.dumps(comparison, indent=2))
    print(json.dumps({"checks": comparison["checks"], "small_change_models_rebuilt_dev_plus_prod": non_breaking}))


if __name__ == "__main__":
    main()
