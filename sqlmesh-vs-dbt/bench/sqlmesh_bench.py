import json
import os
from datetime import datetime, timedelta, timezone

import duckdb
from sqlmesh import Context
from sqlmesh.core.lineage import column_dependencies

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

PROJECT = fresh("sqlmesh")
os.chdir(PROJECT)
DAY_MS = 86400000
LINEAGE_COLUMNS = [
    ("sales.revenue_by_category", "total_revenue"),
    ("sales.daily_revenue", "revenue"),
]
COMMANDS = {
    "initial_build": "sqlmesh plan --auto-apply",
    "audit": "sqlmesh audit",
    "run_no_new_intervals": "sqlmesh run",
    "run_next_interval": "sqlmesh run --execution-time <now + 1 day>",
    "restate_two_days": "sqlmesh plan --restate-model sales.fct_orders --start 2026-01-10 --end 2026-01-11",
    "plan_no_change_prod": "sqlmesh plan",
    "dev_env_no_change": "sqlmesh plan dev --include-unmodified",
    "non_breaking_change_dev": "sqlmesh plan dev --include-unmodified",
    "promote_non_breaking_prod": "sqlmesh plan",
    "breaking_change_dev": "sqlmesh plan dev --include-unmodified",
}


def short(name):
    return ".".join(name.replace('"', "").split(".")[-2:])


def load():
    return Context(paths=str(PROJECT))


def coverage(plan, si):
    kind = plan.snapshots[si.snapshot_id].model.kind
    if kind.is_incremental_by_time_range:
        return f"{len(si.intervals)} daily intervals"
    return "full refresh"


def describe(plan):
    return {
        "models_rebuilt": sorted(short(si.snapshot_id.name) for si in plan.missing_intervals),
        "intervals": {short(si.snapshot_id.name): coverage(plan, si) for si in plan.missing_intervals},
        "changes": sorted(
            ({"model": short(s.name), "category": s.change_category.name} for s in plan.new_snapshots),
            key=lambda c: c["model"],
        ),
    }


def plan_step(environment, **kwargs):
    def work():
        ctx = load()
        plan = ctx.plan_builder(environment, include_unmodified=True, **kwargs).build()
        info = describe(plan)
        ctx.apply(plan)
        ctx.close()
        return info

    info, seconds = timed(work)
    info.update({"seconds": seconds, "environment": environment})
    return info


def interval_days():
    ctx = load()
    env = ctx.state_sync.get_environment("prod")
    snaps = ctx.state_sync.get_snapshots(env.snapshots)
    days = {short(s.name): sum((e - b) // DAY_MS for b, e in s.intervals) for s in snaps.values()}
    ctx.close()
    return days


def run_step(execution_time=None):
    before = interval_days()

    def work():
        ctx = load()
        ctx.run("prod", execution_time=execution_time)
        ctx.close()

    _, seconds = timed(work)
    after = interval_days()
    processed = {m: after[m] - before.get(m, 0) for m in after if after[m] != before.get(m, 0)}
    return {"seconds": seconds, "models_rebuilt": sorted(processed), "intervals": processed}


def audit_step():
    def work():
        ctx = load()
        count = sum(len(m.audits) for m in ctx.models.values())
        ok = ctx.audit(start="2026-01-05", end=datetime.now(timezone.utc).date().isoformat())
        ctx.close()
        return count, ok

    (count, ok), seconds = timed(work)
    return {"seconds": seconds, "models_rebuilt": [], "audits": count, "passed": bool(ok)}


def trace(ctx, model, column, edges):
    if ctx.get_model(model).kind.is_seed:
        return
    for parent, columns in column_dependencies(ctx, model, column).items():
        for parent_column in sorted(columns):
            edge = {"from": f"{short(parent)}.{parent_column}", "to": f"{short(model)}.{column}"}
            if edge not in edges:
                edges.append(edge)
                trace(ctx, parent, parent_column, edges)


def lineage():
    ctx = load()
    out = {}
    for model, column in LINEAGE_COLUMNS:
        edges = []
        trace(ctx, model, column, edges)
        out[f"{model}.{column}"] = edges
    ctx.close()
    return out


def fetch():
    con = duckdb.connect(str(PROJECT / "warehouse.duckdb"), read_only=True)
    results = read_results(con)
    dev_columns = [r[0] for r in con.execute("DESCRIBE sales__dev.stg_orders").fetchall()]
    con.close()
    return results, dev_columns


def main():
    steps = {}
    steps["initial_build"] = plan_step("prod")
    steps["audit"] = audit_step()
    steps["run_no_new_intervals"] = run_step()
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    steps["run_next_interval"] = run_step(execution_time=tomorrow)
    steps["restate_two_days"] = plan_step("prod", restate_models=["sales.fct_orders"], start="2026-01-10", end="2026-01-11")
    steps["plan_no_change_prod"] = plan_step("prod")
    steps["dev_env_no_change"] = plan_step("dev")
    apply_non_breaking(PROJECT)
    steps["non_breaking_change_dev"] = plan_step("dev")
    steps["promote_non_breaking_prod"] = plan_step("prod")
    apply_breaking(PROJECT)
    steps["breaking_change_dev"] = plan_step("dev")
    for name, command in COMMANDS.items():
        steps[name]["command"] = command
    results, dev_columns = fetch()
    report = {
        "tool": "sqlmesh",
        "changes": {"non_breaking": NON_BREAKING, "breaking": BREAKING},
        "steps": steps,
        "column_lineage": lineage(),
        "dev_stg_orders_columns": dev_columns,
        "results": results,
    }
    (RESULTS / "sqlmesh.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: {"seconds": v["seconds"], "models_rebuilt": v["models_rebuilt"]} for k, v in steps.items() if "models_rebuilt" in v}, indent=1))


if __name__ == "__main__":
    main()
