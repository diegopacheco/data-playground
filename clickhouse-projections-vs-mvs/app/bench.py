import json
import math
import os
import statistics
import time
import uuid
import clickhouse as ch
import events
import queries
import schema

RUNS = 21
VARIANTS = ("base", "projection", "view")


def seconds(sql, **settings):
    started = time.perf_counter()
    ch.command(sql, **settings)
    return time.perf_counter() - started


def load(first, batches):
    spent = {variant: [] for variant in VARIANTS}
    for batch in range(batches):
        select = events.select(first + batch * events.BATCH_ROWS, events.BATCH_ROWS)
        turn = batch % len(VARIANTS)
        for variant in VARIANTS[turn:] + VARIANTS[:turn]:
            spent[variant].append(seconds(f"INSERT INTO {schema.TABLES[variant]} {select}"))
    return spent


def write_cost(spent):
    rows = events.BATCH_ROWS * events.LIVE_BATCHES
    return [{
        "variant": variant,
        "rows": rows,
        "seconds": sum(spent[variant]),
        "rows_per_second": rows / sum(spent[variant]),
        "batch_seconds": spent[variant],
    } for variant in VARIANTS]


def stage(name, title):
    totals = {variant: ch.rows(queries.TOTALS[variant])[0][0] for variant in VARIANTS}
    print(f"{name}: " + ", ".join(f"{v} {t['events']} events" for v, t in totals.items()), flush=True)
    return {"id": name, "title": title, **totals}


def backfill():
    statements = {"projection": schema.MATERIALIZE_PROJECTION, "view": schema.BACKFILL_VIEW}
    return {variant: {"statement": " ".join(sql.split()), "seconds": seconds(sql, mutations_sync=2)}
            for variant, sql in statements.items()}


def merge_state():
    database, table = schema.TARGET.split(".")
    return ch.rows(f"""
        SELECT (SELECT count() FROM {schema.TARGET}) AS rows_without_final,
               (SELECT count() FROM {schema.TARGET} FINAL) AS rows_with_final,
               (SELECT uniqExact(day, country, device) FROM {schema.TARGET}) AS groups,
               (SELECT count() FROM system.parts WHERE database = '{database}' AND table = '{table}' AND active) AS parts
    """)[0][0]


def verify():
    for case in queries.CASES:
        results = [ch.rows(queries.sql_for(case, variant))[0] for variant in VARIANTS]
        if not results[0] or any(result != results[0] for result in results):
            raise SystemExit(f"correctness gate failed on {case['id']}: the three variants disagree, no timing reported")
        print(f"correctness gate {case['id']}: {len(results[0])} identical rows from all three variants", flush=True)


def storage():
    parts = ch.rows(f"""
        SELECT concat(database, '.', table) AS name, sum(rows) AS rows, sum(bytes_on_disk) AS bytes, count() AS parts
        FROM system.parts WHERE database = '{schema.DATABASE}' AND active GROUP BY name
    """)[0]
    tables = {part["name"]: part for part in parts}
    projection = ch.rows(f"""
        SELECT sum(rows) AS rows, sum(bytes_on_disk) AS bytes
        FROM system.projection_parts WHERE database = '{schema.DATABASE}' AND active
    """)[0][0]
    extra = {"base": {"rows": 0, "bytes": 0}, "projection": projection, "view": tables[schema.TARGET]}
    sizes = []
    for variant in VARIANTS:
        table = tables[schema.TABLES[variant]]
        raw = table["bytes"] - (projection["bytes"] if variant == "projection" else 0)
        sizes.append({
            "variant": variant,
            "rows": table["rows"],
            "raw_bytes": raw,
            "pre_aggregated_rows": extra[variant]["rows"],
            "pre_aggregated_bytes": extra[variant]["bytes"],
            "total_bytes": raw + extra[variant]["bytes"],
        })
    return sizes


def percentile(samples, fraction):
    return sorted(samples)[math.ceil(fraction * len(samples)) - 1]


def measure(case, variant):
    sql = queries.sql_for(case, variant)
    query_id = str(uuid.uuid4())
    summary = ch.rows(sql, query_id=query_id)[1]
    samples = [ch.rows(sql)[1]["elapsed_ns"] / 1e6 for _ in range(RUNS)]
    return {
        "variant": variant,
        "sql": sql,
        "query_id": query_id,
        "runs": RUNS,
        "median_ms": statistics.median(samples),
        "p95_ms": percentile(samples, 0.95),
        "read_rows": summary["read_rows"],
        "read_bytes": summary["read_bytes"],
    }


def read_latency():
    cases = []
    for case in queries.CASES:
        cases.append({
            "id": case["id"],
            "title": case["title"],
            "note": case["note"],
            "view_reads_target": bool(case["view_sql"]),
            "explain": ch.text("EXPLAIN projections = 1 " + queries.sql_for(case, "projection")),
            "variants": [measure(case, variant) for variant in VARIANTS],
        })
    ch.command("SYSTEM FLUSH LOGS")
    ids = [variant["query_id"] for case in cases for variant in case["variants"]]
    logged = {row["query_id"]: row for row in ch.rows(f"""
        SELECT query_id, projections, read_rows FROM system.query_log
        WHERE type = 'QueryFinish' AND query_id IN {ids}
    """)[0]}
    for case in cases:
        for variant in case["variants"]:
            variant["projections"] = logged[variant["query_id"]]["projections"]
            variant["query_log_read_rows"] = logged[variant["query_id"]]["read_rows"]
    return cases


def mutate(action):
    return {variant: seconds(f"ALTER TABLE {schema.TABLES[variant]} {action}", mutations_sync=2) for variant in VARIANTS}


def main():
    for sql in schema.CREATE_TABLES:
        ch.command(sql)
    load(0, events.HISTORIC_ROWS // events.BATCH_ROWS)
    for sql in (schema.ADD_PROJECTION, schema.CREATE_TARGET, schema.CREATE_VIEW):
        ch.command(sql)
    spent = load(events.HISTORIC_ROWS, events.LIVE_BATCHES)
    stages = [stage("before_backfill", "Projection and view created after the historic rows, then live batches loaded")]

    ch.command(f"SYSTEM STOP MERGES {schema.TARGET}")
    backfilled = backfill()
    merges = merge_state()
    ch.command(f"SYSTEM START MERGES {schema.TARGET}")
    stages.append(stage("after_backfill", "MATERIALIZE PROJECTION and manual INSERT ... SELECT into the view target"))

    verify()
    for table in [*schema.TABLES.values(), schema.TARGET]:
        ch.command(f"OPTIMIZE TABLE {table} FINAL")
    sizes = storage()
    read = read_latency()

    deleted = mutate(f"DELETE WHERE {schema.DELETE_WHERE}")
    stages.append(stage("after_delete", f"ALTER TABLE ... DELETE WHERE {schema.DELETE_WHERE}"))
    updated = mutate(f"UPDATE {schema.UPDATE_SET}")
    stages.append(stage("after_update", f"ALTER TABLE ... UPDATE {schema.UPDATE_SET}"))
    repair = sum(seconds(sql) for sql in schema.REPAIR_VIEW)
    stages.append(stage("after_repair", "TRUNCATE the view target and rebuild it with INSERT ... SELECT"))

    results = {
        "clickhouse": ch.text("SELECT version()"),
        "dataset": events.dataset(),
        "write": write_cost(spent),
        "storage": sizes,
        "backfill": backfilled,
        "merge_state": merges,
        "read": read,
        "stages": stages,
        "mutations": {"delete": deleted, "update": updated, "repair_view_seconds": repair},
    }
    with open(os.environ["RESULTS"], "w") as out:
        json.dump(results, out, indent=1)
    for row in results["write"]:
        print(f"write {row['variant']}: {row['seconds']:.2f}s, {row['rows_per_second']:.0f} rows/s", flush=True)


if __name__ == "__main__":
    main()
