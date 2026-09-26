import datetime
import decimal
import json
import os
import signal
import statistics
import sys
import time
from importlib.metadata import version
from pathlib import Path
from pyspark.sql import SparkSession
from queries import QUERIES

DATA = os.environ.get("DATA_DIR", "/data")
RESULTS = Path(os.environ.get("RESULTS", "/app/results/results.json"))
RUNS = int(os.environ.get("BENCH_RUNS", "5"))
TIMEOUT = int(os.environ.get("BENCH_TIMEOUT", "900"))
PRODUCTS = {"spark": lambda v: f"Apache Spark {v}", "sail": lambda v: f"Sail {version('pysail')} (Spark {v} protocol)"}
ENGINES = {
    "spark": os.environ.get("SPARK_URL", "sc://r2-spark:15002"),
    "sail": os.environ.get("SAIL_URL", "sc://r2-sail:50051"),
}


def normalize(value):
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else round(float(value), 6)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    return value


def collect(df):
    start = time.perf_counter()
    rows = df.collect()
    ms = (time.perf_counter() - start) * 1000
    return ms, [[normalize(v) for v in row] for row in rows], list(df.columns)


def first_line(error):
    text = str(error).strip()
    return text.splitlines()[0][:400] if text else type(error).__name__


def measure(spark, q):
    try:
        cold, rows, columns = collect(q["run"](spark))
        warm = [collect(q["run"](spark))[0] for _ in range(RUNS)]
    except Exception as error:
        return {"supported": False, "error": first_line(error)}
    return {"supported": True, "cold_ms": round(cold, 1), "warm_ms": [round(w, 1) for w in warm],
            "warm_median_ms": round(statistics.median(warm), 1), "columns": columns, "rows": rows}


def session(url):
    spark = SparkSession.builder.remote(url).getOrCreate()
    spark.read.parquet(f"{DATA}/orders").createOrReplaceTempView("orders")
    spark.read.parquet(f"{DATA}/products.parquet").createOrReplaceTempView("products")
    return spark


def run_engine(name, url):
    spark = session(url)
    info = {"url": url, "version": spark.version, "product": PRODUCTS[name](spark.version), "orders_rows": spark.table("orders").count()}
    results = {}
    for q in QUERIES:
        results[q["id"]] = measure(spark, q)
        r = results[q["id"]]
        state = f"cold={r['cold_ms']}ms warm_median={r['warm_median_ms']}ms rows={len(r['rows'])}" if r["supported"] else f"UNSUPPORTED {r['error']}"
        print(f"{name:5} {q['id']} {state}", flush=True)
    spark.stop()
    return info, results


def compare(spark, sail):
    if not (spark["supported"] and sail["supported"]):
        return None
    return spark["rows"] == sail["rows"] and spark["columns"] == sail["columns"]


def speedup(spark, sail):
    if not (spark["supported"] and sail["supported"]) or sail["warm_median_ms"] <= 0:
        return None
    return round(spark["warm_median_ms"] / sail["warm_median_ms"], 2)


def main():
    signal.alarm(TIMEOUT)
    measured = {name: run_engine(name, url) for name, url in ENGINES.items()}
    queries = []
    for q in QUERIES:
        per = {name: measured[name][1][q["id"]] for name in ENGINES}
        identical = compare(per["spark"], per["sail"])
        queries.append({"id": q["id"], "title": q["title"], "kind": q["kind"], "text": q["text"],
                        "identical": identical, "speedup": speedup(per["spark"], per["sail"]), "engines": per})
        print(f"{q['id']} identical={identical} speedup={queries[-1]['speedup']}", flush=True)
    report = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "client": f"pyspark-client {version('pyspark-client')}",
        "warm_runs": RUNS,
        "engines": {name: measured[name][0] for name in ENGINES},
        "queries": queries,
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(report, indent=1))
    different = [q["id"] for q in queries if q["identical"] is False]
    unsupported = [q["id"] for q in queries if q["identical"] is None]
    print(f"identical: {sum(1 for q in queries if q['identical'])}/{len(queries)}, different: {different or 'none'}, unsupported: {unsupported or 'none'}")
    if different:
        sys.exit(f"engines returned different results for {', '.join(different)}")


if __name__ == "__main__":
    main()
