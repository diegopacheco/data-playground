import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

import dataset
import rawcols
from checksums import table_checksums
from formats import FORMATS, file_path, load_source, nimble_dump, run_step

LAKE = os.environ.get("LAKE", "/lake")
RESULTS = os.environ.get("RESULTS", "/bench/results/results.json")
ITERATIONS = int(os.environ.get("ITERATIONS", "5"))
WIDE_ROWS = int(os.environ.get("WIDE_ROWS", "10000"))
WIDE_COLS = int(os.environ.get("WIDE_COLS", "4000"))
NORMAL_ROWS = int(os.environ.get("NORMAL_ROWS", "1000000"))
SWEEP_ROWS = int(os.environ.get("SWEEP_ROWS", "2000"))
SWEEP_COLS = [int(c) for c in os.environ.get("SWEEP_COLS", "100,1000,4000,10000").split(",")]
PROJECT_WIDE = int(os.environ.get("PROJECT_WIDE", "5"))
PROJECT_NORMAL = int(os.environ.get("PROJECT_NORMAL", "2"))


def log(message):
    print(f"[bench] {message}", flush=True)


def summary(runs):
    warm = runs[1:] or runs
    return {"cold": round(runs[0], 3), "median": round(statistics.median(warm), 3), "runs": [round(r, 3) for r in runs]}


def prepare(name, table):
    table_dir = os.path.join(LAKE, name)
    shutil.rmtree(table_dir, ignore_errors=True)
    os.makedirs(table_dir)
    rawcols.write_dir(table, os.path.join(table_dir, "source"))
    with pa.OSFile(os.path.join(table_dir, "source.arrow"), "wb") as f:
        with pa.ipc.new_file(f, table.schema) as writer:
            writer.write_table(table)
    return table_dir, {"rows": table.num_rows, "columns": table.num_columns, "arrow_bytes": table.nbytes,
                       "checksums": table_checksums(table)}


def child(*args):
    out = subprocess.run([sys.executable, os.path.abspath(__file__), *map(str, args)], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"bench {' '.join(map(str, args))} failed ({out.returncode}): {out.stderr.strip()[-2000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def generate(kind, rows, columns, seed):
    if kind == "wide":
        return dataset.wide_table(rows, columns, seed=seed)
    return dataset.normal_table(rows, seed=seed)


def prepare_child(name, kind, rows, columns, seed, project_count):
    table = generate(kind, int(rows), int(columns), int(seed))
    projected = dataset.projection(table, int(project_count))
    table_dir, source = prepare(name, table)
    return dict(source, table_dir=table_dir, projection=projected)


def parquet_equal(fmt, table_dir):
    return pq.read_table(file_path(table_dir, fmt)).equals(load_source(table_dir))


def full_equal(fmt, table_dir):
    if fmt == "nimble":
        dump_dir = os.path.join(table_dir, "nimble_dump")
        shutil.rmtree(dump_dir, ignore_errors=True)
        nimble_dump(table_dir, dump_dir)
        equal = rawcols.same_bytes(os.path.join(table_dir, "source"), dump_dir)
        shutil.rmtree(dump_dir, ignore_errors=True)
        return equal
    return child("parquet_equal", fmt, table_dir)


def measure(fmt, table_dir, source, columns, iterations):
    log(f"{os.path.basename(table_dir)} {fmt}")
    write = run_step(fmt, "write", table_dir, iterations)
    scan = run_step(fmt, "scan", table_dir, iterations)
    project = run_step(fmt, "project", table_dir, iterations, columns)
    meta = run_step(fmt, "meta", table_dir, iterations)
    checks = {
        "rows": scan["rows"] == source["rows"] and project["rows"] == source["rows"],
        "scan_checksums": scan["checksums"] == source["checksums"],
        "project_checksums": project["checksums"] == {c: source["checksums"][c] for c in columns},
        "project_columns": sorted(project["checksums"]) == sorted(columns),
        "meta_columns": meta["columns"] == source["columns"],
        "full_equal": full_equal(fmt, table_dir),
    }
    return {
        "name": fmt,
        "size_bytes": write["size_bytes"],
        "footer_bytes": meta["footer_bytes"], "metadata_bytes": meta.get("metadata_bytes", meta["footer_bytes"]),
        "schema_bytes": meta.get("schema_bytes"),
        "parts": meta.get("stripes", meta.get("row_groups")),
        "write_ms": summary(write["write_ms"]),
        "scan_ms": summary(scan["scan_ms"]),
        "project_ms": summary(project["scan_ms"]),
        "meta_ms": summary(meta["meta_ms"]),
        "scan_checksums": scan["checksums"] if len(scan["checksums"]) <= 16 else None,
        "project_checksums": project["checksums"],
        "checks": checks,
        "ok": all(checks.values()),
    }


def run_table(name, kind, rows, columns, seed, project_count, iterations):
    source = child("prepare", name, kind, rows, columns, seed, project_count)
    table_dir, columns = source["table_dir"], source["projection"]
    formats = [measure(fmt, table_dir, source, columns, iterations) for fmt in FORMATS]
    return {
        "name": name, "rows": source["rows"], "columns": source["columns"], "arrow_bytes": source["arrow_bytes"],
        "projection": columns,
        "source_checksums": {c: source["checksums"][c] for c in columns},
        "formats": formats,
        "ok": all(f["ok"] for f in formats),
    }


def sweep_point(columns, iterations):
    source = child("prepare", f"sweep_{columns}", "wide", SWEEP_ROWS, columns, columns, PROJECT_WIDE)
    table_dir, projected = source["table_dir"], source["projection"]
    formats = []
    for fmt in FORMATS:
        log(f"sweep {columns} {fmt}")
        write = run_step(fmt, "write", table_dir, iterations)
        project = run_step(fmt, "project", table_dir, iterations, projected)
        meta = run_step(fmt, "meta", table_dir, iterations)
        ok = project["checksums"] == {c: source["checksums"][c] for c in projected} and meta["columns"] == columns
        formats.append({"name": fmt, "size_bytes": write["size_bytes"], "footer_bytes": meta["footer_bytes"], "metadata_bytes": meta.get("metadata_bytes", meta["footer_bytes"]),
                        "write_ms": summary(write["write_ms"]), "project_ms": summary(project["scan_ms"]),
                        "meta_ms": summary(meta["meta_ms"]), "ok": ok})
    shutil.rmtree(table_dir, ignore_errors=True)
    return {"columns": columns, "rows": SWEEP_ROWS, "formats": formats, "ok": all(f["ok"] for f in formats)}


def versions():
    found = {"python": platform.python_version(), "pyarrow": pa.__version__, "numpy": np.__version__}
    for key in ("NIMBLE_COMMIT", "VELOX_COMMIT"):
        path = os.path.join(os.path.dirname(os.environ.get("NIMBLE_BENCH", "/opt/nimble/nimble_bench")), key)
        if os.path.exists(path):
            found[key.lower()] = open(path).read().strip()
    return found


def main():
    started = time.time()
    runs = ITERATIONS + 1
    tables = [
        run_table("wide", "wide", WIDE_ROWS, WIDE_COLS, 42, PROJECT_WIDE, runs),
        run_table("normal", "normal", NORMAL_ROWS, 8, 7, PROJECT_NORMAL, runs),
    ]
    sweep = [sweep_point(c, runs) for c in SWEEP_COLS]
    results = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(time.time() - started, 1),
        "iterations": ITERATIONS,
        "cpus": os.cpu_count(),
        "versions": versions(),
        "tables": tables,
        "sweep": sweep,
        "all_ok": all(t["ok"] for t in tables) and all(s["ok"] for s in sweep),
    }
    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w") as f:
        json.dump(results, f, indent=1)
    log(f"done in {results['elapsed_s']}s all_ok={results['all_ok']}")
    for t in tables:
        for f in t["formats"]:
            log(f"{t['name']:6} {f['name']:15} size={f['size_bytes']:>11} write={f['write_ms']['median']:>9} "
                f"scan={f['scan_ms']['median']:>9} project={f['project_ms']['median']:>8} meta={f['meta_ms']['median']:>7} ok={f['ok']}")
    if not results["all_ok"]:
        raise SystemExit("verification failed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "prepare":
        print(json.dumps(prepare_child(*sys.argv[2:])))
    elif len(sys.argv) > 1 and sys.argv[1] == "parquet_equal":
        print(json.dumps(parquet_equal(sys.argv[2], sys.argv[3])))
    else:
        main()
