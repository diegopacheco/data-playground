import json
import os
import sys
import time
import numpy as np
import config
from dataset import generate, exact_top
from engine_duckdb import DuckdbVss
from engine_pgvector import Pgvector
from engine_qdrant import Qdrant

IDS = os.path.join(config.RUN, "ids")


def save(name, rows):
    with open(os.path.join(IDS, name + ".txt"), "w") as f:
        f.writelines(" ".join(map(str, row)) + "\n" for row in rows)


def measure(search, queries):
    for q in queries[:config.WARMUP]:
        search(q)
    found, latency = [], []
    for q in queries:
        started = time.perf_counter()
        ids = search(q)
        latency.append(time.perf_counter() - started)
        found.append(ids)
    return found, latency


def summary(found, truth, latency):
    p50, p95, p99 = np.percentile(latency, [50, 95, 99]) * 1000
    return {
        "recall": float(np.mean([len(set(a) & set(b)) / config.K for a, b in zip(found, truth)])),
        "returned": float(np.mean([len(a) for a in found])),
        "p50_ms": float(p50),
        "p95_ms": float(p95),
        "p99_ms": float(p99),
        "qps": len(latency) / sum(latency),
    }


def run(engine, vectors, queries, buckets, truth, filtered_truth):
    print(f"{engine.name}: building", flush=True)
    result = {"name": engine.name, "label": engine.label, "version": engine.version(), "deployment": engine.deployment, "parameters": engine.parameters}
    result.update(engine.build(vectors, buckets))
    result["sweep"], result["filtered"] = [], []
    for ef in config.EF_SEARCH:
        engine.set_ef(ef)
        found, latency = measure(engine.search, queries)
        save(f"{engine.name}-ef{ef}", found)
        result["sweep"].append({"ef": ef} | summary(found, truth, latency))
        print(f"{engine.name}: ef {ef} recall {result['sweep'][-1]['recall']:.4f}", flush=True)
    engine.set_ef(config.FILTERED_EF)
    result["plan"] = engine.plan(queries[0], False)
    for n, (variant, prepare) in enumerate(engine.filtered_variants()):
        prepare()
        found, latency = measure(engine.search_filtered, queries[:config.FILTERED_QUERIES])
        save(f"{engine.name}-filtered{n}", found)
        result["filtered"].append({"variant": variant, "file": f"{engine.name}-filtered{n}", "ef": config.FILTERED_EF, "plan": engine.plan(queries[0], True)} | summary(found, filtered_truth, latency))
        print(f"{engine.name}: filtered {variant} recall {result['filtered'][-1]['recall']:.4f}", flush=True)
    return result


def main():
    os.makedirs(IDS, exist_ok=True)
    vectors, queries, buckets = generate()
    ids = np.arange(config.ROWS)
    started = time.perf_counter()
    truth = exact_top(vectors, ids, queries, config.K)
    match = buckets == config.BUCKET
    filtered_truth = exact_top(vectors[match], ids[match], queries[:config.FILTERED_QUERIES], config.K)
    truth_seconds = time.perf_counter() - started
    save("truth", truth)
    save("truth-filtered", filtered_truth)
    save("buckets", enumerate(buckets.tolist()))
    np.savetxt(os.path.join(config.RUN, "probe-queries.txt"), queries[:20], fmt="%.9g", delimiter=",")
    settings = {k.lower(): getattr(config, k) for k in ("SEED", "ROWS", "DIM", "CLUSTERS", "SPREAD", "QUERIES", "FILTERED_QUERIES", "WARMUP", "K", "M", "EF_CONSTRUCTION", "EF_SEARCH", "FILTERED_EF", "BUCKETS", "BUCKET", "BUILD_THREADS")}
    settings |= {"metric": "L2 (Euclidean)", "filter_matches": int(match.sum()), "truth_seconds": truth_seconds, "numpy": np.__version__, "python": sys.version.split()[0]}
    engines = [run(cls(), vectors, queries, buckets, truth, filtered_truth) for cls in (DuckdbVss, Pgvector, Qdrant)]
    with open(os.path.join(config.RUN, "results.json"), "w") as f:
        json.dump({"measured_at": time.strftime("%Y-%m-%d %H:%M:%S"), "settings": settings, "engines": engines}, f, indent=1)


if __name__ == "__main__":
    main()
