import os
import threading
import time
from datetime import datetime, timezone
import psycopg
import data
import kafka_io
import pipeline

DSN = os.environ.get("RW_DSN", "postgresql://root@localhost:4566/dev")
LOCK = threading.Lock()
STATE = {"phase": "empty", "sent": {"orders": 0, "payments": 0}, "target": {}, "log": [], "before": None, "after": None}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def note(message):
    STATE["log"].append({"at": now(), "message": message})
    STATE["log"] = STATE["log"][-40:]


def plain(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def query(sql, params=None):
    with psycopg.connect(DSN, autocommit=True) as conn:
        cur = conn.execute(sql, params)
        names = [c.name for c in cur.description]
        return [{n: plain(v) for n, v in zip(names, row)} for row in cur.fetchall()]


def execute(statements):
    with psycopg.connect(DSN, autocommit=True) as conn:
        for sql, params in statements:
            conn.execute(sql, params)


def ingested():
    orders = query("SELECT count(*) AS orders, coalesce(sum(version), 0) AS versions FROM orders")[0]
    payments = query("SELECT coalesce(max(payments), 0) AS payments FROM mv_payment_count")[0]
    return {"orders": orders["orders"], "versions": orders["versions"], "payments": payments["payments"]}


def snapshot():
    return {name: query(sql) for name, sql in pipeline.VIEWS.items()}


def sink():
    records = kafka_io.read_topic("region_revenue")
    return {"records": records, "compacted": sorted(kafka_io.compact(records), key=lambda r: r["region"])}


def reset():
    STATE.update(phase="resetting", sent={"orders": 0, "payments": 0}, target={}, before=None, after=None)
    STATE["log"] = []
    execute([(sql, None) for sql in pipeline.drop_statements()])
    kafka_io.recreate_topics()
    note("topics orders, payments, region_revenue recreated")
    execute([(sql, None) for _, _, sql in pipeline.OBJECTS])
    note(f"created {len(pipeline.OBJECTS)} objects: tables, source, materialized views, sink")
    customers = data.build()["customers"]
    execute([("INSERT INTO customers VALUES (%s, %s, %s)", (c["customer_id"], c["name"], c["region"])) for c in customers] + [("FLUSH", None)])
    note(f"inserted {len(customers)} customers")
    STATE["phase"] = "ready"


def interleave(orders, payments):
    by_order = {}
    for p in payments:
        by_order.setdefault(p["order_id"], []).append(p)
    events = []
    for order in sorted(orders, key=lambda o: o["event_time"]):
        events.append(("orders", order["order_id"], order))
        events.extend(("payments", p["payment_id"], p) for p in by_order.get(order["order_id"], []))
    return events


def produce(events, rate):
    producer = kafka_io.Producer()
    try:
        for topic, key, value in events:
            producer.send(topic, key, value)
            STATE["sent"][topic] += 1
            if rate:
                producer.producer.flush()
                time.sleep(1 / rate)
    finally:
        producer.close()


def wait_for(target, seconds=60):
    STATE["target"] = target
    deadline = time.time() + seconds
    while time.time() < deadline:
        if ingested() == target:
            return
        time.sleep(0.5)
    raise TimeoutError(f"risingwave did not ingest {target}, has {ingested()}")


def base_target(d):
    return {"orders": len(d["orders"]), "versions": len(d["orders"]), "payments": len(d["payments"])}


def final_target(d):
    c = d["corrections"]
    return {
        "orders": len(d["orders"]) + len(c["late_orders"]),
        "versions": len(d["orders"]) + len(c["updated_orders"]) + len(c["late_orders"]),
        "payments": len(d["payments"]) + len(c["late_payments"]),
    }


def correct(d, rate):
    c = d["corrections"]
    moved = c["moved_customer"]
    execute([("UPDATE customers SET region = %s WHERE customer_id = %s", (moved["region"], moved["customer_id"])), ("FLUSH", None)])
    note(f"customer {moved['customer_id']} moved to {moved['region']}")
    events = [("orders", o["order_id"], o) for o in c["updated_orders"]]
    events += [("orders", o["order_id"], o) for o in c["late_orders"]]
    events += [("payments", p["payment_id"], p) for p in c["late_payments"]]
    produce(events, rate)
    note(f"sent {len(c['updated_orders'])} updated orders, {len(c['late_orders'])} late orders, {len(c['late_payments'])} late payments")


def run(base_rate=0, correction_rate=0, pause=0):
    d = data.build()
    reset()
    STATE["phase"] = "feeding base"
    STATE["target"] = base_target(d)
    produce(interleave(d["orders"], d["payments"]), base_rate)
    note(f"sent {len(d['orders'])} orders and {len(d['payments'])} payments")
    wait_for(base_target(d))
    STATE["before"] = snapshot()
    note("base ingested, snapshot taken")
    time.sleep(pause)
    STATE["phase"] = "correcting"
    STATE["target"] = final_target(d)
    correct(d, correction_rate)
    wait_for(final_target(d))
    STATE["after"] = snapshot()
    STATE["phase"] = "done"
    note("corrections ingested, snapshot taken")
    return {"before": STATE["before"], "after": STATE["after"], "ran_at": now()}


def run_all():
    with LOCK:
        try:
            return run()
        except Exception as e:
            STATE["phase"] = "failed"
            note(f"failed: {type(e).__name__}: {e}")
            raise


def live():
    if not LOCK.acquire(blocking=False):
        return False

    def worker():
        try:
            run(base_rate=25, correction_rate=2, pause=3)
        except Exception as e:
            STATE["phase"] = "failed"
            note(f"failed: {type(e).__name__}: {e}")
        finally:
            LOCK.release()

    threading.Thread(target=worker, daemon=True).start()
    return True


def view():
    result = {"phase": STATE["phase"], "sent": STATE["sent"], "target": STATE["target"], "log": STATE["log"]}
    try:
        result["ingested"] = ingested()
        result["mvs"] = snapshot()
    except psycopg.Error as e:
        result["error"] = str(e).strip()
    return result
