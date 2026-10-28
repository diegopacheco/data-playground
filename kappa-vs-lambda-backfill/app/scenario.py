import inspect
import time
from datetime import datetime, timezone

import db
import eventlog
import gen
import kappa_arch
import lambda_arch
import pipeline
import rules

REPORT = {}


def check(name, ok, detail=""):
    return {"name": name, "ok": bool(ok), "detail": detail}


def on_day(rows, day):
    return [r for r in rows if r[0] == day]


def mismatches(rows, truth):
    a = {(r[0], r[1]): r for r in rows}
    b = {(r[0], r[1]): r for r in truth}
    return sorted(f"{k[0]} {k[1]}" for k in set(a) | set(b) if a.get(k) != b.get(k))


def log_stats(events):
    ids = [e["event_id"] for e in events]
    return {"sent": len(ids), "distinct": len(set(ids)), "resends": len(ids) - len(set(ids)), "late": sum(1 for i in set(ids) if i.startswith("late"))}


class Run:
    def __init__(self):
        self.steps = []
        self.metrics = {}

    def add(self, sid, arch, title, text, started, checks_fn, extra=None):
        snap = pipeline.views()
        checks = checks_fn(snap)
        self.steps.append({
            "id": sid,
            "arch": arch,
            "title": title,
            "text": text,
            "ms": round((time.perf_counter() - started) * 1000, 1),
            "checks": checks,
            "extra": extra or {},
            "snapshot": snap,
        })
        return snap


def produce_phase(phase):
    events = gen.phase_events(phase)
    pipeline.produce(events)
    return log_stats(events)


def run():
    with pipeline.LOCK:
        r = Run()
        day = gen.DAYS[0]

        t = time.perf_counter()
        pipeline.reset()
        r.add("reset", "both", "Empty log, empty tables, logic v1 everywhere",
              "The orders topic is recreated with infinite retention, Postgres is recreated, Lambda batch and speed run logic v1 and the Kappa job v1 serves kappa_serving.",
              t, lambda s: [check("log is empty", s["log_end_offset"] == 0), check("nothing served yet", not s["lambda_serving"] and not s["kappa_serving"])])

        t = time.perf_counter()
        stats = produce_phase(1)
        r.add("produce-1", "log", "4 days of orders, 3% sent twice",
              "Days 2026-09-20..23 go to Redpanda in event time order. The upstream retries about 3% of the events, so the same event_id is in the log twice.",
              t, lambda s: [
                  check("upstream resent events", stats["resends"] > 0, f"{stats['resends']} resends"),
                  check("Lambda serving equals truth v1", s["lambda_serving"] == s["truth_v1"]),
                  check("Kappa serving equals truth v1", s["kappa_serving"] == s["truth_v1"]),
                  check("each event counted once", sum(x[2] + x[3] for x in s["kappa_serving"]) == stats["distinct"], f"{stats['distinct']} distinct events"),
              ], stats)

        t = time.perf_counter()
        nightly = lambda_arch.batch(advance=True)
        pipeline.catch_up()
        r.add("lambda-nightly-1", "lambda", "Lambda nightly batch absorbs everything",
              "The batch layer recomputes every day from the master dataset up to the watermark, then the speed layer is reset to start at the watermark.",
              t, lambda s: [
                  check("batch view equals truth v1", s["lambda_batch"] == s["truth_v1"]),
                  check("speed view is empty after the batch", not s["lambda_speed"]),
                  check("serving equals truth v1", s["lambda_serving"] == s["truth_v1"]),
              ], {"batch": nightly})

        t = time.perf_counter()
        stats = produce_phase(2)
        late = r.add("late-data", "both", "Late orders for 09-20 and 09-21 arrive with 09-24",
                     "100 events with an old event time arrive after the nightly batch, plus 25 resends of old events. Lambda keeps them in the speed layer, Kappa updates the old day in place.",
                     t, lambda s: [
                         check("late events arrived", stats["late"] == 100, f"{stats['late']} late events"),
                         check("Lambda batch view for 09-20 is stale", on_day(s["lambda_batch"], day) != on_day(s["truth_v1"], day)),
                         check("Lambda speed view holds 09-20 late rows", bool(on_day(s["lambda_speed"], day))),
                         check("Lambda serving (batch + speed) equals truth v1", s["lambda_serving"] == s["truth_v1"]),
                         check("Kappa serving equals truth v1", s["kappa_serving"] == s["truth_v1"]),
                     ], stats)

        t = time.perf_counter()
        first = lambda_arch.batch(days=[day])
        second = lambda_arch.batch(days=[day])
        r.add("lambda-backfill-day", "lambda", "Lambda backfill of 09-20, twice",
              "DELETE + INSERT of one day partition in one transaction, from the deduplicated master dataset, up to the same watermark.",
              t, lambda s: [
                  check("run 1 and run 2 give the same checksum", first["checksum"] == second["checksum"], first["checksum"]["md5"]),
                  check("run 1 and run 2 give the same rows", first["rows"] == second["rows"]),
                  check("serving still equals truth v1", s["lambda_serving"] == s["truth_v1"]),
                  check("no duplicate rows in the partition", first["checksum"]["rows"] == len(gen.STORES)),
              ], {"run1": first, "run2": second})

        t = time.perf_counter()
        before = late["kappa_serving"]
        kfirst = kappa_arch.backfill_day(day)
        ksecond = kappa_arch.backfill_day(day)
        r.add("kappa-backfill-day", "kappa", "Kappa backfill of 09-20, twice",
              "Replay the log from offset 0, keep the first copy of each event_id of 09-20, overwrite the 09-20 rows of the active version in one transaction.",
              t, lambda s: [
                  check("run 1 and run 2 give the same checksum", kfirst["checksum"] == ksecond["checksum"], kfirst["checksum"]["md5"]),
                  check("backfill equals what the live job computed", s["kappa_serving"] == before),
                  check("Kappa serving equals truth v1", s["kappa_serving"] == s["truth_v1"]),
              ], {"run1": kfirst, "run2": ksecond})

        t = time.perf_counter()
        with db.tx() as cur:
            cur.execute("SELECT count(*) FROM lambda_master")
            master_before = cur.fetchone()[0]
        before = pipeline.views()
        pipeline.rewind()
        with db.tx() as cur:
            cur.execute("SELECT count(*) FROM lambda_master")
            master_after = cur.fetchone()[0]
        r.add("redelivery", "both", "At-least-once redelivery of the whole log",
              "Every consumer offset is rewound (Lambda master to 0, speed to the watermark, Kappa to 0) and the log is consumed again.",
              t, lambda s: [
                  check("Lambda master rows unchanged", master_before == master_after, f"{master_after} rows"),
                  check("Lambda serving unchanged", s["lambda_serving"] == before["lambda_serving"]),
                  check("Kappa serving unchanged", s["kappa_serving"] == before["kappa_serving"]),
              ], {"events_redelivered": before["log_end_offset"], "master_rows": master_after})

        t = time.perf_counter()
        nightly2 = lambda_arch.batch(advance=True)
        pipeline.catch_up()
        r.add("lambda-nightly-2", "lambda", "Next Lambda nightly batch absorbs the late data",
              "The watermark moves past the late events, the batch view for 09-20 and 09-21 now includes them and the speed layer starts empty again.",
              t, lambda s: [
                  check("batch view equals truth v1", s["lambda_batch"] == s["truth_v1"]),
                  check("speed view is empty", not s["lambda_speed"]),
              ], {"batch": nightly2})

        t = time.perf_counter()
        stats = produce_phase(3)
        r.add("produce-3", "log", "More live orders and a late 09-22 batch",
              "These events sit in the Lambda speed layer when the bug is found.",
              t, lambda s: [
                  check("speed layer holds data", bool(s["lambda_speed"])),
                  check("Lambda serving equals truth v1", s["lambda_serving"] == s["truth_v1"]),
                  check("Kappa serving equals truth v1", s["kappa_serving"] == s["truth_v1"]),
              ], stats)

        t = time.perf_counter()
        bug = r.add("bug-found", "both", "Bug found: refunds were added to revenue",
                    "Both architectures report revenue = sales + refunds. The fix is revenue = sales - refunds.",
                    t, lambda s: [
                        check("truth v1 and truth v2 differ", s["truth_v1"] != s["truth_v2"]),
                        check("revenue is overstated by twice the refunds", sum(x[4] for x in s["truth_v1"]) - sum(x[4] for x in s["truth_v2"]) > 0),
                    ], {"rules": rules.RULES})

        t = time.perf_counter()
        lambda_arch.deploy("batch", "v2")
        fixed_batch = lambda_arch.batch()
        watermark = fixed_batch["watermark"]
        batch_truth = pipeline.truth("v2", watermark)
        mixed = r.add("lambda-fix-batch", "lambda", "Lambda fix, step 1: new batch SQL and a full backfill",
                      "The SQL of the batch layer is changed and every day is recomputed. The speed layer still runs the old Python code.",
                      t, lambda s: [
                          check("batch view equals truth v2 up to the watermark", s["lambda_batch"] == batch_truth),
                          check("serving is a mix of v2 and v1 (wrong)", s["lambda_serving"] != s["truth_v2"], ", ".join(mismatches(s["lambda_serving"], s["truth_v2"]))),
                      ], {"batch": fixed_batch})
        lambda_batch_ms = r.steps[-1]["ms"]

        t = time.perf_counter()
        speed_offset_end = eventlog.end_offset()
        lambda_arch.deploy("speed", "v2")
        pipeline.catch_up()
        r.add("lambda-fix-speed", "lambda", "Lambda fix, step 2: same fix again in the speed layer",
              "The Python code of the speed layer gets the same fix, the speed view is dropped and rebuilt from the watermark.",
              t, lambda s: [check("Lambda serving equals truth v2", s["lambda_serving"] == s["truth_v2"])],
              {"events_reread": speed_offset_end - watermark})
        lambda_speed_ms = r.steps[-1]["ms"]

        t = time.perf_counter()
        rep1 = kappa_arch.replay("v2", "v2")
        rep2 = kappa_arch.replay("v2", "v2")
        r.add("kappa-replay", "kappa", "Kappa fix: replay the log from offset 0 into kappa_daily_v2, twice",
              "The same streaming job with the fixed code reads the topic from the start into a new table. v1 keeps serving meanwhile.",
              t, lambda s: [
                  check("replay 1 and replay 2 give the same checksum", rep1["checksum"] == rep2["checksum"], rep1["checksum"]["md5"]),
                  check("kappa_daily_v2 equals truth v2", rep2["rows"] == s["truth_v2"]),
                  check("kappa_serving still serves v1 (no mixed state)", s["kappa_serving"] == s["truth_v1"]),
              ], {"run1": rep1, "run2": rep2})

        t = time.perf_counter()
        swapped = kappa_arch.swap("v2")
        v1_rows = pipeline.table(kappa_arch.daily("v1"))
        r.add("kappa-swap", "kappa", "Kappa swap: kappa_serving now reads kappa_daily_v2",
              "One CREATE OR REPLACE VIEW. The v1 job is retired and its table is kept for rollback.",
              t, lambda s: [
                  check("Kappa serving equals truth v2", s["kappa_serving"] == s["truth_v2"]),
                  check("v1 table kept, equal to truth v1", v1_rows == s["truth_v1"]),
              ], swapped)
        kappa_swap_ms = r.steps[-1]["ms"]

        t = time.perf_counter()
        stats = produce_phase(4)
        final = r.add("after-fix", "both", "New live and late orders after the fix",
                      "Both pipelines keep running with the fixed logic, including late data and resends.",
                      t, lambda s: [
                          check("Lambda serving equals truth v2", s["lambda_serving"] == s["truth_v2"]),
                          check("Kappa serving equals truth v2", s["kappa_serving"] == s["truth_v2"]),
                          check("Lambda and Kappa agree", s["lambda_serving"] == s["kappa_serving"]),
                      ], stats)

        compare = {
            "lambda": {
                "logic_implementations": 2,
                "logic_code": [lambda_arch.BATCH_SQL["v2"], inspect.getsource(rules.revenue_delta)],
                "jobs": ["master ingest (log to master dataset)", "speed layer (Python, incremental)", "batch layer (SQL, nightly)"],
                "tables": ["lambda_master", "lambda_batch_view", "lambda_speed_view", "lambda_speed_seen", "lambda_serving (view)"],
                "fix_deploys": 2,
                "fix_ms": round(lambda_batch_ms + lambda_speed_ms, 1),
                "fix_reads": fixed_batch["master_rows_scanned"] + (speed_offset_end - watermark),
                "fix_reads_detail": f"{fixed_batch['master_rows_scanned']} master rows + {speed_offset_end - watermark} log events",
                "wrong_rows_during_fix": len(mismatches(mixed["lambda_serving"], mixed["truth_v2"])),
                "late_data": "speed layer serves it until the next nightly batch absorbs it",
                "idempotency": "master dataset keyed by event_id, day partitions overwritten in one transaction",
                "reprocess_source": "master dataset in Postgres",
            },
            "kappa": {
                "logic_implementations": 1,
                "logic_code": [inspect.getsource(rules.revenue_delta)],
                "jobs": ["one streaming job per version (v1 live, v2 replaying, then v2 live)"],
                "tables": ["kappa_daily_v1", "kappa_seen_v1", "kappa_daily_v2", "kappa_seen_v2", "kappa_serving (view)"],
                "fix_deploys": 1,
                "fix_ms": round(rep1["ms"] + kappa_swap_ms, 1),
                "fix_reads": rep1["events_replayed"],
                "fix_reads_detail": f"{rep1['events_replayed']} log events replayed from offset 0",
                "wrong_rows_during_fix": 0,
                "late_data": "the streaming job updates the old day in place when the event arrives",
                "idempotency": "event_id dedup table and output + offset in one transaction per version",
                "reprocess_source": "the Redpanda topic with infinite retention",
            },
            "final_equal": final["lambda_serving"] == final["kappa_serving"],
            "bug_overstatement_cents": sum(x[4] for x in bug["truth_v1"]) - sum(x[4] for x in bug["truth_v2"]),
        }

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ok": all(c["ok"] for s in r.steps for c in s["checks"]),
            "days": gen.DAYS,
            "stores": gen.STORES,
            "rules": rules.RULES,
            "steps": r.steps,
            "compare": compare,
        }
        REPORT.clear()
        REPORT.update(report)
        return report
