import threading
import time
import uuid

import db
import eventlog
import gen
import kappa_arch
import lambda_arch
import rules

LOCK = threading.RLock()
STATE = {"ready": False, "last_error": None}


def reset():
    with LOCK:
        STATE["ready"] = False
        eventlog.recreate_topic()
        with db.tx() as cur:
            cur.execute(db.SCHEMA)
        kappa_arch.create_job("v1", "v1")
        kappa_arch.swap("v1")
        STATE["ready"] = True


def catch_up():
    with LOCK:
        end = eventlog.end_offset()
        lambda_arch.ingest_master(end)
        lambda_arch.speed(end)
        kappa_arch.run_jobs(end)
        return end


def truth(logic, end=None):
    end = eventlog.end_offset() if end is None else end
    return rules.to_rows(rules.aggregate(rules.first_seen(eventlog.read(0, end)), logic))


def produce(events):
    with LOCK:
        eventlog.produce(events)
        catch_up()
    return len(events)


def produce_live(kind, count):
    if kind not in ("late", "live") or not 0 < count <= 5000:
        raise ValueError("kind must be late or live and count 1..5000")
    events = gen.live_events(kind, count, f"{kind}-{uuid.uuid4().hex[:8]}")
    return {"kind": kind, "sent": produce(events), "day": events[0]["ts"][:10]}


def rewind():
    with LOCK:
        lambda_arch.rewind()
        kappa_arch.rewind()
        catch_up()


def locked(fn, *args):
    with LOCK:
        result = fn(*args)
        catch_up()
        return result


def state():
    if not STATE["ready"]:
        return {"ready": False, "last_error": STATE["last_error"]}
    with LOCK:
        end = eventlog.end_offset()
        with db.tx() as cur:
            cfg = lambda_arch.config(cur)
            master = db.get_offset(cur, "lambda_master")
            speed = db.get_offset(cur, "lambda_speed")
            cur.execute("SELECT count(*) FROM lambda_master")
            master_rows = cur.fetchone()[0]
            jobs = kappa_arch.jobs(cur)
            act = kappa_arch.active(cur)
    for j in jobs:
        j["lag"] = end - j["next_offset"]
    return {
        "ready": True,
        "last_error": STATE["last_error"],
        "log_end_offset": end,
        "lambda": {**cfg, "master_offset": master, "master_rows": master_rows, "speed_offset": speed, "master_lag": end - master, "speed_lag": end - speed},
        "kappa": {"active": act["version"], "jobs": jobs},
    }


def views():
    with LOCK:
        end = eventlog.end_offset()
        with db.tx() as cur:
            out = {
                "log_end_offset": end,
                "lambda_serving": db.rows(cur, "lambda_serving"),
                "lambda_batch": db.rows(cur, "lambda_batch_view"),
                "lambda_speed": db.rows(cur, "lambda_speed_view"),
                "kappa_serving": db.rows(cur, "kappa_serving"),
            }
        out["truth_v1"] = truth("v1", end)
        out["truth_v2"] = truth("v2", end)
        return out


def table(relation):
    with db.tx() as cur:
        return db.rows(cur, relation)


def loop():
    while True:
        time.sleep(1)
        if not STATE["ready"]:
            continue
        try:
            catch_up()
            STATE["last_error"] = None
        except Exception as e:
            STATE["last_error"] = str(e)


def start_background():
    threading.Thread(target=loop, daemon=True).start()
