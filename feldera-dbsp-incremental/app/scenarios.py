import statistics
import time
import data
import feldera
import recompute

VIEWS = ["region_totals", "hourly_revenue", "reachable"]
SIZES = [62_500, 125_000, 250_000, 500_000, 1_000_000]
DELTA_SIZES = [10, 100, 1_000, 10_000, 100_000]
REPEATS = 5
LOAD_BATCH = 125_000
FRESH_IDS = 10_000_000


def order_steps():
    return [
        ("insert orders 1..40", "orders", [{"insert": data.order(i)} for i in range(1, 41)]),
        ("insert orders 41..60", "orders", [{"insert": data.order(i)} for i in range(41, 61)]),
        ("delete orders 5, 10, .., 50", "orders", [{"delete": {"id": i}} for i in range(5, 51, 5)]),
        ("update amount of orders 1, 2, 3", "orders", [{"insert": {**data.order(i), "amount": 9_000 + i}} for i in (1, 2, 3)]),
        ("insert 10 graph edges", "edges", [{"insert": {"src": s, "dst": d}} for s, d in data.GRAPH]),
        ("delete edge 3 -> 4", "edges", [{"delete": {"src": 3, "dst": 4}}]),
        ("insert edge 9 -> 10", "edges", [{"insert": {"src": 9, "dst": 10}}]),
        ("delete edge 6 -> 3, insert edge 6 -> 1", "edges", [{"delete": {"src": 6, "dst": 3}}, {"insert": {"src": 6, "dst": 1}}]),
    ]


def snapshot():
    return {view: feldera.query(f"SELECT * FROM {view}") for view in VIEWS}


def changes():
    feldera.ensure_running()
    feldera.restart_empty()
    listeners = {view: feldera.Listener(view) for view in VIEWS}
    log = []
    try:
        for label, table, updates in order_steps():
            seen = {view: len(lst.changes()) for view, lst in listeners.items()}
            started = time.perf_counter()
            step = feldera.push(table, updates)
            elapsed = (time.perf_counter() - started) * 1000
            for lst in listeners.values():
                lst.caught_up(step)
            deltas = {view: lst.changes()[seen[view]:] for view, lst in listeners.items()}
            log.append({"label": label, "table": table, "updates": updates, "step": step, "ms": round(elapsed, 2), "deltas": deltas})
        streamed = {view: lst.changes() for view, lst in listeners.items()}
    finally:
        for lst in listeners.values():
            lst.close()
    return {"steps": log, "streamed": streamed, "snapshot": snapshot()}


def timed(fn, repeats):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return round(statistics.median(samples), 2)


def fixed_change(state, size, fresh):
    victims = state.oldest(size // 2)
    rows = [data.order(fresh + i) for i in range(size - len(victims))]
    return victims, rows


def apply_change(state, listeners, victims, rows):
    updates = [{"delete": {"id": i}} for i in victims] + [{"insert": r} for r in rows]
    seen = sum(len(lst.changes()) for lst in listeners)
    started = time.perf_counter()
    step = feldera.push("orders", updates)
    elapsed = (time.perf_counter() - started) * 1000
    for lst in listeners:
        lst.caught_up(step)
    state.apply(victims, rows)
    return elapsed, sum(len(lst.changes()) for lst in listeners) - seen


def scaling():
    feldera.ensure_running()
    feldera.restart_empty()
    state = recompute.State()
    listeners = [feldera.Listener("region_totals"), feldera.Listener("hourly_revenue")]
    fresh = FRESH_IDS
    by_size = []
    by_delta = []
    try:
        loaded = 0
        for size in SIZES:
            load_ms = 0.0
            while loaded < size:
                stop = min(size, loaded + LOAD_BATCH)
                rows = data.orders(loaded, stop)
                started = time.perf_counter()
                feldera.push_csv("orders", data.csv_rows(rows))
                load_ms += (time.perf_counter() - started) * 1000
                state.load(rows)
                loaded = stop
            feldera_ms = []
            outputs = []
            for _ in range(REPEATS):
                victims, rows = fixed_change(state, 20, fresh)
                fresh += len(rows)
                ms, out = apply_change(state, listeners, victims, rows)
                feldera_ms.append(ms)
                outputs.append(out)
            by_size.append({
                "rows": state.count(),
                "load_ms": round(load_ms, 1),
                "feldera_delta_ms": round(statistics.median(feldera_ms), 2),
                "output_changes": max(outputs),
                "duckdb_full_ms": timed(state.duckdb_views, 3),
                "python_full_ms": timed(state.python_views, 1 if size >= 500_000 else 3),
            })
        for size in DELTA_SIZES:
            samples = []
            for _ in range(3):
                victims, rows = fixed_change(state, size, fresh)
                fresh += len(rows)
                samples.append(apply_change(state, listeners, victims, rows)[0])
            by_delta.append({"rows": state.count(), "changed_rows": size, "feldera_delta_ms": round(statistics.median(samples), 2)})
    finally:
        for lst in listeners:
            lst.close()
    feldera_totals = feldera.query("SELECT * FROM region_totals")
    feldera_hourly = feldera.query("SELECT * FROM hourly_revenue")
    duck_totals, duck_hourly = state.duckdb_views()
    py_totals, py_hourly = state.python_views()
    return {
        "by_size": by_size,
        "by_delta": by_delta,
        "final": {
            "rows": state.count(),
            "loaded_ids": [0, SIZES[-1]],
            "deleted_ids": sorted(state.deleted),
            "inserted_ids": [FRESH_IDS, fresh],
            "region_totals": feldera_totals,
            "hourly_revenue": feldera_hourly,
            "matches_duckdb": recompute.normalize(feldera_totals) == duck_totals and recompute.normalize(feldera_hourly) == duck_hourly,
            "matches_python": recompute.normalize(feldera_totals) == py_totals and recompute.normalize(feldera_hourly) == py_hourly,
        },
    }


def pipeline():
    state = feldera.status() or {}
    stats = feldera.stats() if state.get("deployment_status") == "Running" else {}
    metrics = stats.get("global_metrics", {})
    return {
        "name": feldera.PIPELINE,
        "program_code": feldera.PROGRAM,
        "program_status": state.get("program_status"),
        "deployment_status": state.get("deployment_status"),
        "storage_status": state.get("storage_status"),
        "platform_version": state.get("platform_version"),
        "runtime_config": {"workers": (state.get("runtime_config") or {}).get("workers")},
        "metrics": {k: metrics.get(k) for k in ("total_input_records", "total_processed_records", "rss_bytes", "buffered_input_records", "total_completed_steps")},
        "inputs": [{"name": i.get("endpoint_name"), "records": (i.get("metrics") or {}).get("total_records")} for i in stats.get("inputs", [])],
        "outputs": [{"name": o.get("endpoint_name"), "records": (o.get("metrics") or {}).get("transmitted_records")} for o in stats.get("outputs", [])],
    }


def deploy():
    feldera.ensure_running()
    return pipeline()


SCENARIOS = {"scaling": scaling, "changes": changes}
