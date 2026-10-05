import json
import sys

from workspace import ROOT

d = json.loads((ROOT / "comparison.json").read_text())
rows = {s["scenario"]: s for s in d["scenarios"]}
failures = []


def check(label, condition):
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        failures.append(label)


def models(scenario, tool):
    return rows[scenario][tool]["models"]


check("both tools produce identical revenue_by_category and daily_revenue", d["checks"]["results_identical"])
check("revenue_by_category equals the awk computation from the raw CSV", d["checks"]["revenue_by_category_matches_awk"])
check("all 200 orders are counted in revenue_by_category", sum(r["total_orders"] for r in d["results"]["sqlmesh"]["revenue_by_category"]) == 200)
check("SQLMesh dev environment without changes recomputes nothing (virtual layer)", models("Create dev environment, no change", "sqlmesh") == [])
check("dbt dev target without changes rebuilds seed plus 4 models", len(models("Create dev environment, no change", "dbt")) == 5)
check("SQLMesh non-breaking change backfills only stg_orders", models("Non-breaking change in dev", "sqlmesh") == ["sales.stg_orders"])
check("SQLMesh promotion of a dev-tested change recomputes nothing", models("Promote non-breaking change to prod", "sqlmesh") == [])
check("dbt state:modified+ rebuilds stg_orders and its 3 children for the same change", len(models("Non-breaking change in dev", "dbt")) == 4)
check("SQLMesh breaking change rebuilds stg_orders and every downstream model", len(models("Breaking change in dev", "sqlmesh")) == 4)
check("SQLMesh no-new-interval run does nothing", models("Incremental run, no new data", "sqlmesh") == [])
check("SQLMesh restatement touches only 2 daily intervals of fct_orders", rows["Reprocess 2026-01-10..11 of fct_orders"]["sqlmesh"]["detail"]["intervals"]["sales.fct_orders"] == "2 daily intervals")
check("dbt incremental run selects zero new rows and keeps 200 rows", rows["Incremental run, no new data"]["dbt"]["detail"]["rows_matching_incremental_filter"] == 0 and rows["Incremental run, no new data"]["dbt"]["detail"]["fct_orders_rows_after"] == 200)
categories = {c["model"]: c["category"] for c in d["classification"]["non_breaking"]}
check("adding a column is classified NON_BREAKING with INDIRECT_NON_BREAKING children", categories.get("sales.stg_orders") == "NON_BREAKING" and categories.get("sales.fct_orders") == "INDIRECT_NON_BREAKING")
categories = {c["model"]: c["category"] for c in d["classification"]["breaking"]}
check("adding a WHERE filter is classified BREAKING with INDIRECT_BREAKING children", categories.get("sales.stg_orders") == "BREAKING" and categories.get("sales.daily_revenue") == "INDIRECT_BREAKING")
lineage = d["lineage"]["sqlmesh_columns"]["sales.revenue_by_category.total_revenue"]
check("column lineage traces total_revenue to raw.orders.price and raw.orders.quantity", {"raw.orders.price", "raw.orders.quantity"} <= {e["from"] for e in lineage})
check("audits and tests all pass", rows["Run tests / audits"]["sqlmesh"]["detail"]["passed"] and rows["Run tests / audits"]["dbt"]["detail"]["tests_passed"] == rows["Run tests / audits"]["dbt"]["detail"]["tests"])

sys.exit(1 if failures else 0)
