import time
import uuid
import gravitino
import lineage
import marquez
import warehouse
from model import table

RAW = table("raw", "raw_orders")
CLEAN = table("clean", "clean_orders")
REVENUE = table("gold", "revenue_by_category")

JOBS = [
    {"name": "load_raw_orders", "description": "copy data/orders.csv into raw.raw_orders", "sql": warehouse.LOAD_RAW_SQL,
     "inputs": lambda: [lineage.file_dataset("data/orders.csv", warehouse.csv_header())], "output": RAW, "step": warehouse.load_raw},
    {"name": "build_clean_orders", "description": "validate orders, hash the customer and compute the amount", "sql": warehouse.BUILD_CLEAN_SQL,
     "inputs": lambda: [lineage.table_dataset(RAW)], "output": CLEAN, "step": warehouse.build_clean},
    {"name": "build_revenue_by_category", "description": "aggregate clean orders into revenue per category", "sql": warehouse.BUILD_REVENUE_SQL,
     "inputs": lambda: [lineage.table_dataset(CLEAN)], "output": REVENUE, "step": warehouse.build_revenue},
]


def run_job(spec):
    run_id = uuid.uuid7()
    job = lineage.job(spec["name"], spec["description"], spec["sql"])
    inputs = spec["inputs"]()
    output = lineage.table_dataset(spec["output"])
    lineage.emit(lineage.event("START", run_id, job, inputs, [output]))
    started = time.perf_counter()
    try:
        rows = spec["step"]()
    except Exception as e:
        lineage.emit(lineage.event("FAIL", run_id, job, inputs, [output], lineage.error_facet(e)))
        raise
    lineage.emit(lineage.event("COMPLETE", run_id, job, inputs, [lineage.with_row_count(output, rows)]))
    print(f"{spec['name']:<27} run {run_id}  rows {rows:>4}  {1000 * (time.perf_counter() - started):7.1f} ms  START+COMPLETE sent to gravitino")
    return run_id


def main():
    print(f"gravitino {gravitino.version()} at {gravitino.GRAVITINO_URL}")
    for kind, name, state in gravitino.ensure_catalog():
        print(f"{kind:<9} {name:<36} {state}")
    run_ids = [run_job(spec) for spec in JOBS]
    started = time.perf_counter()
    states = marquez.wait_for_runs(run_ids)
    print(f"marquez recorded {len(states)} runs as COMPLETED after {time.perf_counter() - started:.1f} s (gravitino lineage http sink)")


if __name__ == "__main__":
    main()
