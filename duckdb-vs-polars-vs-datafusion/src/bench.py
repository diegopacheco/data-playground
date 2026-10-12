import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import pyarrow.parquet as pq
from engines import ENGINES, ORDERS, version
from queries import COLUMNS, SQL, TITLES

ROOT = Path(__file__).resolve().parent.parent
RUNS = int(os.environ.get("BENCH_RUNS", "7"))


def measure(engine, q):
    out = subprocess.run([sys.executable, str(ROOT / "src" / "worker.py"), engine, q, str(RUNS)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def bench_query(q):
    results = {e: measure(e, q) for e in ENGINES}
    rows = {e: r.pop("rows") for e, r in results.items()}
    reference = rows["duckdb"]
    identical = all(r == reference for r in rows.values())
    print(f"{q} identical={identical} rows={len(reference)} " + " ".join(
        f"{e}:cold={r['cold_ms']}ms warm={r['warm_median_ms']}ms peak={r['peak_rss_mb']}MB" for e, r in results.items()))
    return {"id": q, "title": TITLES[q], "sql": SQL[q], "columns": COLUMNS[q], "identical": identical,
            "row_count": len(reference), "result": reference, "engines": results}


def main():
    queries = [bench_query(q) for q in SQL]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "machine": f"{platform.system()} {platform.machine()} cpus={os.cpu_count()}",
        "dataset_rows": pq.ParquetFile(ORDERS).metadata.num_rows,
        "dataset_mb": round(Path(ORDERS).stat().st_size / 1e6, 1),
        "warm_runs": RUNS,
        "versions": {e: version(e) for e in ENGINES},
        "queries": queries,
    }
    (ROOT / "results.json").write_text(json.dumps(report, indent=2))
    if not all(q["identical"] for q in queries):
        sys.exit("engines returned different results")
    print("all engines returned identical results for every query")


if __name__ == "__main__":
    main()
