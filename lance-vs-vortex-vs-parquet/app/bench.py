import gc
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

import vector
from dataset import BASE_SCHEMA, DIM, checksums, expand, load_base, normalize
from formats import FILTER_CATEGORY, FILTER_MIN_QUANTITY, FORMATS, PROJECTION, remove, size_of

ROOT = Path(__file__).resolve().parent.parent
ROWS = int(os.environ.get("ROWS", "1000000"))
ITERATIONS = int(os.environ.get("ITERATIONS", "5"))
TAKE_N = int(os.environ.get("TAKE_N", "100"))
QUERIES = int(os.environ.get("QUERIES", "20"))
K = 10
LAKE = Path(os.environ.get("LAKE", ROOT / ".lake"))
RESULTS = Path(os.environ.get("RESULTS", ROOT / "results" / "results.json"))


def timed(fn, *args):
    gc.collect()
    start = time.perf_counter()
    out = fn(*args)
    return (time.perf_counter() - start) * 1000, out


def stats(cold, warm):
    return {"cold": round(cold, 2), "median": round(statistics.median(warm), 2), "runs": [round(r, 2) for r in warm]}


def take_indices(rows, n, seed=99):
    return sorted(int(i) for i in np.random.default_rng(seed).choice(rows, n, replace=False))


def expected_filter(table):
    mask = pc.and_(pc.equal(table.column("category"), FILTER_CATEGORY),
                   pc.greater_equal(table.column("quantity"), FILTER_MIN_QUANTITY))
    return table.filter(mask).select(PROJECTION)


def sorted_projection(table):
    return table.select(PROJECTION).cast(pa.schema([BASE_SCHEMA.field(c) for c in PROJECTION])).sort_by("order_id").combine_chunks()


def lake_path(fmt):
    return LAKE / f"orders.{fmt.ext}"


def run_once(fmt, table, indices):
    path = lake_path(fmt)
    remove(path)
    write_ms, _ = timed(fmt.write, table, path)
    scan_ms, scanned = timed(fmt.scan, path)
    scanned = None
    filter_ms, _ = timed(fmt.filter, path)
    take_ms, _ = timed(fmt.take, path, indices)
    return write_ms, scan_ms, filter_ms, take_ms


def verify(fmt, table, indices, source_sums):
    path = lake_path(fmt)
    scanned = normalize(fmt.scan(path))
    sums = checksums(scanned)
    filtered = sorted_projection(fmt.filter(path))
    taken = normalize(fmt.take(path, indices))
    return {
        "scan_equal": scanned.equals(table),
        "checksums": sums,
        "checksums_equal": sums == source_sums,
        "filter_rows": filtered.num_rows,
        "filter_equal": filtered.equals(sorted_projection(expected_filter(table))),
        "take_rows": taken.num_rows,
        "take_equal": taken.equals(normalize(table.take(pa.array(indices)))),
    }


def run_format(fmt, table, indices, source_sums):
    print(f"benchmarking {fmt.name}", flush=True)
    cold = run_once(fmt, table, indices)
    warm = []
    for i in range(ITERATIONS):
        warm.append(run_once(fmt, table, indices))
        w, s, f, t = warm[-1]
        print(f"  {fmt.name} run {i + 1}/{ITERATIONS} write={w:.0f}ms scan={s:.0f}ms filter={f:.1f}ms take={t:.2f}ms", flush=True)
    scalar_path = LAKE / f"scalar.{fmt.ext}"
    remove(scalar_path)
    fmt.write(table.drop_columns(["embedding"]), scalar_path)
    result = {
        "name": fmt.name,
        "settings": fmt.settings,
        "size_bytes": size_of(lake_path(fmt)),
        "scalar_size_bytes": size_of(scalar_path),
        "checks": verify(fmt, table, indices, source_sums),
    }
    remove(scalar_path)
    for n, metric in enumerate(("write_ms", "scan_ms", "filter_ms", "take_ms")):
        result[metric] = stats(cold[n], [w[n] for w in warm])
    result["ok"] = all(result["checks"][c] for c in ("scan_equal", "checksums_equal", "filter_equal", "take_equal"))
    return result


def run_vector(table):
    fmt = next(f for f in FORMATS if f.name == "lance")
    path = lake_path(fmt)
    data_bytes = size_of(path)
    print("building lance IVF_PQ index", flush=True)
    build_ms, _ = timed(vector.build_index, path)
    vectors = table.column("embedding").combine_chunks().values.to_numpy().reshape(-1, DIM)
    categories = table.column("category").to_pylist()
    rows = np.random.default_rng(5).choice(len(vectors), QUERIES, replace=False)
    ann, flat, recalls, same_category = [], [], [], []
    for row in rows:
        query = vectors[row]
        ms, found = timed(vector.nearest, path, query, K)
        ann.append(ms)
        flat.append(timed(vector.nearest, path, query, K, False)[0])
        recalls.append(vector.recall(found.column("order_id").to_pylist(), vector.exact(vectors, query, K)))
        same_category.append(sum(c == categories[row] for c in found.column("category").to_pylist()) / K)
    sample_row = int(rows[0])
    sample = vector.nearest(path, vectors[sample_row], K)
    print(f"  ann={statistics.median(ann):.1f}ms flat={statistics.median(flat):.1f}ms recall@{K}={statistics.mean(recalls):.3f}", flush=True)
    return {
        "column": vector.COLUMN,
        "dim": DIM,
        "index": vector.INDEX,
        "search": vector.SEARCH,
        "build_ms": round(build_ms, 2),
        "index_bytes": size_of(path) - data_bytes,
        "k": K,
        "queries": QUERIES,
        "ann_ms": stats(ann[0], ann[1:]),
        "flat_ms": stats(flat[0], flat[1:]),
        "recall_at_k": round(statistics.mean(recalls), 4),
        "same_category": round(statistics.mean(same_category), 4),
        "sample": {
            "row": sample_row,
            "order_id": sample_row + 1,
            "product": table.column("product")[sample_row].as_py(),
            "category": categories[sample_row],
            "results": sample.to_pylist(),
        },
    }


def versions():
    return {"python": platform.python_version(), **{p: version(p) for p in ("pyarrow", "pylance", "vortex-data", "numpy")}}


def run_source(table):
    return {
        "rows": ROWS,
        "iterations": ITERATIONS,
        "take_n": TAKE_N,
        "cpus": os.cpu_count(),
        "versions": versions(),
        "arrow_bytes": table.nbytes,
        "arrow_scalar_bytes": table.drop_columns(["embedding"]).nbytes,
        "filter": {
            "sql": f"SELECT {', '.join(PROJECTION)} WHERE category = '{FILTER_CATEGORY}' AND quantity >= {FILTER_MIN_QUANTITY}",
            "expected_rows": expected_filter(table).num_rows,
        },
        "source_checksums": checksums(table),
    }


def run_step(name):
    base = load_base(ROOT / "data" / "orders.csv")
    table = normalize(expand(base, ROWS))
    if name == "source":
        return run_source(table)
    if name == "vector":
        return run_vector(table)
    fmt = next(f for f in FORMATS if f.name == name)
    return run_format(fmt, table, take_indices(ROWS, TAKE_N), checksums(table))


def step_in_process(name):
    out = LAKE / f"step-{name}.json"
    subprocess.run([sys.executable, __file__, name], check=True)
    part = json.loads(out.read_text())
    out.unlink()
    return part


def main():
    LAKE.mkdir(parents=True, exist_ok=True)
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    report = step_in_process("source")
    print(f"{ROWS} rows, arrow size {report['arrow_bytes'] / 1e6:.1f} MB, each step runs in its own process", flush=True)
    results = [step_in_process(fmt.name) for fmt in FORMATS]
    report["formats"] = results
    report["vector"] = step_in_process("vector")
    report["all_ok"] = all(r["ok"] for r in results) and report["vector"]["recall_at_k"] >= 0.9
    RESULTS.write_text(json.dumps(report, indent=2))
    print(f"{'format':<10}{'size MB':>10}{'write':>10}{'scan':>10}{'filter':>10}{'take':>10}  ok")
    for r in results:
        print(f"{r['name']:<10}{r['size_bytes'] / 1e6:>10.2f}{r['write_ms']['median']:>10.1f}{r['scan_ms']['median']:>10.1f}"
              f"{r['filter_ms']['median']:>10.1f}{r['take_ms']['median']:>10.2f}  {r['ok']}")
    print(f"wrote {RESULTS.name} all_ok={report['all_ok']}")
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        (LAKE / f"step-{sys.argv[1]}.json").write_text(json.dumps(run_step(sys.argv[1])))
        sys.exit(0)
    sys.exit(main())
