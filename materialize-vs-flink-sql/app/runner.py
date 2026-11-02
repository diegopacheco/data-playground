import time
from datetime import datetime, timezone
import flink
import kafka_io
import materialize
import oracle
from data import events, phases
from queries import QUERIES

PAUSE = 0.6
TOPICS = ["orders", "customers"]


def topics_for(run_id):
    return {t: f"{t}_{run_id}" for t in TOPICS}


def summarize_flink(changelog):
    kinds = {}
    for r in changelog:
        kinds[r[0]] = kinds.get(r[0], 0) + 1
    return kinds


def checks(result):
    expected = result["expected"]
    prefixes = set(oracle.totals_prefixes(events()))
    mz_totals = [tuple(s[1]) for s in oracle.mz_states(result["materialize"]["changelog"]["totals"]) if len(s) == 2]
    fl_totals = [tuple(s[1]) for s in oracle.flink_states(result["flink"]["changelog"]["totals"]) if len(s) == 2]
    probes = result["materialize"]["probes"]
    return {
        "results": {name: {"materialize": result["materialize"]["final"]["results"][name] == expected[name],
                           "flink": result["flink"]["results"][name] == expected[name]} for name in QUERIES},
        "probe_invariant_breaks": sum(1 for p in probes if not (p[1] == p[3] == p[6] and p[2] == p[4] == p[5] == p[7])),
        "probe_phantoms": sum(1 for p in probes if (p[1], p[2] if p[1] else None) not in prefixes),
        "mz_states": len(mz_totals),
        "mz_phantoms": sum(1 for s in mz_totals if s not in prefixes),
        "flink_states": len(fl_totals),
        "flink_phantoms": sum(1 for s in fl_totals if s not in prefixes),
    }


def run():
    run_id = f"r{int(time.time())}"
    topics = topics_for(run_id)
    materialize.drop()
    kafka_io.recreate_topics([f"{t}_r" for t in TOPICS], list(topics.values()))
    statements, start = materialize.setup(topics)
    probe = materialize.Probe()
    producer = kafka_io.Producer(topics)
    log = []
    try:
        for p in phases():
            if p["name"] == "inserts":
                probe.start()
            ms = producer.send(p["events"])
            log.append({"name": p["name"], "events": len(p["events"]), "ms": ms})
            if p["name"] == "customers":
                materialize.wait_ingested("customers_src", producer.offsets[topics["customers"]])
            time.sleep(PAUSE)
        final = materialize.read_all(real_time_recency=True)
    finally:
        probe.stop()
        producer.close()
    offsets = {t: {"produced": producer.offsets[t], "ingested": materialize.ingested(f"{k}_src")} for k, t in topics.items()}
    end = materialize.now() + 1
    mz = {
        "ddl": statements,
        "start": start,
        "end": end,
        "final": final,
        "offsets": offsets,
        "probes": probe.samples,
        "probe_errors": probe.errors,
        "changelog": {name: materialize.subscribe(name, start, end) for name in QUERIES},
    }
    fl = flink.run_all(topics)
    fl["kinds"] = {name: summarize_flink(rows) for name, rows in fl["changelog"].items()}
    result = {
        "run_id": run_id,
        "topics": topics,
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "phases": log,
        "events": events(),
        "queries": QUERIES,
        "expected": oracle.answers(events()),
        "materialize": mz,
        "flink": fl,
    }
    result["checks"] = checks(result)
    return result
