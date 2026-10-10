import gc
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

import fastavro
import pyarrow as pa

from dataset import expand, load_base
from formats import VARIANTS, aggregate, label, projected_sum, row_count

ROOT = Path(__file__).resolve().parent.parent
ROWS = int(os.environ.get("ROWS", "1000000"))
ITERATIONS = int(os.environ.get("ITERATIONS", "5"))
LAKE = ROOT / ".lake"
RESULTS = ROOT / "results" / "results.json"


def timed(fn, *args):
    gc.collect()
    start = time.perf_counter()
    out = fn(*args)
    return (time.perf_counter() - start) * 1000, out


def stats(runs):
    return {"median": round(statistics.median(runs), 2), "runs": [round(r, 2) for r in runs]}


def same(left, right):
    if left.keys() != right.keys():
        return False
    for c in left:
        a, b = left[c], right[c]
        if a["orders"] != b["orders"] or a["quantity"] != b["quantity"]:
            return False
        if abs(a["revenue"] - b["revenue"]) > 0.01:
            return False
    return True


def run_variant(variant, table):
    path = LAKE / f"{label(variant)}.{variant.ext}"
    writes, reads, projects = [], [], []
    data = projected = None
    for i in range(ITERATIONS):
        data = projected = None
        writes.append(timed(variant.write, table, path)[0])
        ms, data = timed(variant.read, path)
        reads.append(ms)
        data = None
        ms, projected = timed(variant.project, path)
        projects.append(ms)
        print(f"  {label(variant)} iteration {i + 1}/{ITERATIONS} write={writes[-1]:.0f}ms read={reads[-1]:.0f}ms project={projects[-1]:.0f}ms", flush=True)
    data = variant.read(path)
    return {
        "name": label(variant),
        "format": variant.format,
        "codec": variant.codec,
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "write_ms": stats(writes),
        "read_ms": stats(reads),
        "project_ms": stats(projects),
        "rows_read": row_count(data),
        "projected_sum": projected_sum(projected),
        "aggregation": aggregate(data),
    }


def main():
    LAKE.mkdir(exist_ok=True)
    RESULTS.parent.mkdir(exist_ok=True)
    base = load_base(ROOT / "data" / "orders.csv")
    ms, table = timed(expand, base, ROWS)
    print(f"expanded {base.num_rows} base rows to {table.num_rows} rows in {ms:.0f}ms", flush=True)
    source = aggregate(table)
    total_quantity = sum(v["quantity"] for v in source.values())
    results = []
    for variant in VARIANTS:
        print(f"benchmarking {label(variant)}", flush=True)
        results.append(run_variant(variant, table))
    reference = results[0]["aggregation"]
    for r in results:
        r["aggregation_matches_csv"] = same(r["aggregation"], reference)
        r["rows_ok"] = r["rows_read"] == ROWS
        r["projection_ok"] = r["projected_sum"] == total_quantity
    report = {
        "rows": ROWS,
        "iterations": ITERATIONS,
        "projected_column": "quantity",
        "versions": {
            "python": platform.python_version(),
            "pyarrow": pa.__version__,
            "fastavro": fastavro.__version__,
        },
        "source_matches_csv": same(source, reference),
        "csv_reference": reference,
        "results": results,
    }
    report["all_ok"] = report["source_matches_csv"] and all(
        r["aggregation_matches_csv"] and r["rows_ok"] and r["projection_ok"] for r in results
    )
    RESULTS.write_text(json.dumps(report, indent=2))
    print(f"{'variant':<20}{'size MB':>10}{'write ms':>10}{'read ms':>10}{'proj ms':>10}  ok")
    for r in results:
        ok = r["aggregation_matches_csv"] and r["rows_ok"] and r["projection_ok"]
        print(f"{r['name']:<20}{r['size_bytes'] / 1e6:>10.2f}{r['write_ms']['median']:>10.1f}{r['read_ms']['median']:>10.1f}{r['project_ms']['median']:>10.1f}  {ok}")
    print(f"wrote {RESULTS.relative_to(ROOT)} all_ok={report['all_ok']}")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
