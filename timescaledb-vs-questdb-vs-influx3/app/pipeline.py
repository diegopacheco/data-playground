import hashlib
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
import dataset
import influx
import questdb
import timescale

RAW = ["downsample_1h", "downsample_1m", "last_value", "range_scan"]


def log(text):
    print(text, flush=True)


def load(engine):
    engine.setup()
    payloads = [engine.encode(chunk) for chunk in dataset.batches()]
    started = time.perf_counter()
    with ThreadPoolExecutor(dataset.WORKERS) as pool:
        list(pool.map(engine.send, payloads))
    while engine.count() != dataset.POINTS:
        time.sleep(0.05)
    seconds = time.perf_counter() - started
    log(f"{engine.LABEL}: {dataset.POINTS} rows in {seconds:.1f}s")
    return {"seconds": round(seconds, 2), "rows_per_s": round(dataset.POINTS / seconds)}


def measure(engine, names):
    out = {}
    for name in names:
        times = []
        for _ in range(dataset.RUNS):
            started = time.perf_counter()
            rows = engine.query(name)
            times.append((time.perf_counter() - started) * 1000)
        times.sort()
        out[name] = {"median_ms": round(statistics.median(times), 2), "p95_ms": round(times[round(0.95 * (len(times) - 1))], 2),
                     "rows": len(rows), "statements": len(engine.QUERIES[name]), "sql": " ".join(engine.QUERIES[name][0].split())}
        log(f"{engine.LABEL}: {name} median {out[name]['median_ms']} ms")
    return out


def lines(engine, name):
    return sorted("%s %d %.6f %.6f %.6f" % row for row in engine.hourly(engine.query(name)))


def digest(engine, name):
    return hashlib.md5("\n".join(lines(engine, name)).encode()).hexdigest()


def rollup(engine):
    started = time.perf_counter()
    engine.build_rollup()
    seconds = time.perf_counter() - started
    log(f"{engine.LABEL}: rollup built in {seconds:.1f}s")
    return {"kind": engine.ROLLUP, "build_seconds": round(seconds, 2)}


def run(engine):
    result = {"label": engine.LABEL, "version": engine.version(), "ingest": load(engine)}
    result["disk"] = engine.disk()
    return result


def finish(engine, result):
    result["rollup"] = rollup(engine)
    result["queries"].update(measure(engine, ["rollup_1h"]))
    result["hourly_md5"] = digest(engine, "downsample_1h")
    result["rollup_md5"] = digest(engine, "rollup_1h")
    return result


def main():
    engines = {}

    t = run(timescale)
    t["queries_rowstore"] = measure(timescale, RAW)
    started = time.perf_counter()
    timescale.compress()
    t["compress_seconds"] = round(time.perf_counter() - started, 2)
    t["disk_columnstore"] = timescale.disk()
    t["queries"] = measure(timescale, RAW)
    engines["timescaledb"] = finish(timescale, t)

    q = run(questdb)
    q["queries"] = measure(questdb, RAW)
    engines["questdb"] = finish(questdb, q)

    i = {"label": influx.LABEL, "version": influx.version(), "ingest": load(influx)}
    i["parquet_seconds"] = influx.persist()
    i["disk"] = influx.disk()
    i["full_range_sql"] = " ".join(influx.FULL_RANGE.split())
    i["full_range_error"] = influx.full_range_error()
    i["queries"] = measure(influx, RAW)
    engines["influx3"] = finish(influx, i)

    out = {
        "dataset": {"devices": dataset.DEVICES, "days": dataset.DAYS, "step_seconds": dataset.STEP, "points": dataset.POINTS,
                    "seed": dataset.SEED, "start": dataset.START, "batch": dataset.BATCH, "workers": dataset.WORKERS,
                    "runs": dataset.RUNS},
        "engines": engines,
    }
    os.makedirs(os.path.dirname(dataset.RESULTS), exist_ok=True)
    with open(dataset.RESULTS, "w") as f:
        json.dump(out, f, indent=1)
    log("results written to .run/results.json")


if __name__ == "__main__":
    main()
