import os
import subprocess
import sys
import time
import consumer
import service
import store

APP = os.path.dirname(os.path.abspath(__file__))
CUSTOMERS = 30
ORDERS = 50
ROLLBACKS = 20
LATE_ORDERS = 20
CRASH_ORDERS = 50
CRASH_AT = [7, 19, 23, 38, 44]
VARIANTS = ["outbox", "db-first", "kafka-first"]
TIERS = ["bronze", "silver", "gold"]


class Abort(Exception):
    pass


def log(message):
    print(message, flush=True)


def unique(events):
    return len({e["id"] for e in events})


def wait_unique(expected):
    for _ in range(60):
        events = store.read(store.OUTBOX_TOPICS)
        if unique(events) >= expected:
            return events
        time.sleep(1)
    raise SystemExit(f"expected {expected} unique events on kafka, got {unique(events)}")


def wait_stable():
    previous = -1
    for _ in range(60):
        events = store.read(store.OUTBOX_TOPICS)
        if len(events) == previous:
            return events
        previous = len(events)
        time.sleep(1)
    raise SystemExit("kafka message count never settled")


def wait_flushed(con, lsn):
    for _ in range(60):
        if store.scalar(con, "SELECT confirmed_flush_lsn > %s::pg_lsn FROM pg_replication_slots WHERE slot_name = 's3_outbox'", (lsn,)):
            return
        time.sleep(1)
    raise SystemExit("debezium never confirmed its offsets to postgres")


def podman(*args):
    subprocess.run(["podman", *args], check=True, stdout=subprocess.DEVNULL)


def committed(con):
    for n in range(1, CUSTOMERS + 1):
        with con.transaction():
            service.register_customer(con, f"U-{n:04d}", f"customer {n}", TIERS[n % 3])
    for n in range(1, ORDERS + 1):
        with con.transaction():
            service.place_order(con, f"O-{n:04d}", f"U-{n % CUSTOMERS + 1:04d}", 20 + n)
    for _ in range(2):
        for n in range(1, ORDERS + 1):
            with con.transaction():
                service.advance_order(con, f"O-{n:04d}")
    expected = CUSTOMERS + ORDERS * 3
    events = wait_unique(expected)
    log(f"committed: {expected} transactions, {len(events)} messages, {unique(events)} unique events")
    return expected


def rolled_back(con):
    for n in range(1, ROLLBACKS + 1):
        try:
            with con.transaction():
                service.place_order(con, f"R-{n:04d}", "U-0001", 50 if n % 2 else 0)
                raise Abort()
        except (Abort, store.psycopg.errors.CheckViolation):
            pass
    store.set_fact(con, "rollback_attempts", ROLLBACKS)
    log(f"rolled back: {ROLLBACKS} transactions, {ROLLBACKS // 2} aborted by the service, {ROLLBACKS // 2} rejected by a CHECK constraint")


def deleted(con, expected):
    before = len(store.read(store.OUTBOX_TOPICS))
    lsn = store.scalar(con, "SELECT pg_current_wal_lsn()::text")
    removed = con.execute("DELETE FROM outbox").rowcount
    with con.transaction():
        service.register_customer(con, f"U-{CUSTOMERS + 1:04d}", f"customer {CUSTOMERS + 1}", TIERS[0])
    wait_unique(expected + 1)
    wait_flushed(con, lsn)
    after = store.read(store.OUTBOX_TOPICS)
    store.set_fact(con, "delete_outbox_rows", removed)
    store.set_fact(con, "delete_messages_before", before)
    store.set_fact(con, "delete_messages_after", len(after))
    log(f"deleted {removed} outbox rows: {before} messages before, {len(after)} after one marker event")
    return expected + 1


def restarted(con, expected):
    for n in range(1, ORDERS + 1):
        with con.transaction():
            service.advance_order(con, f"O-{n:04d}")
    expected += ORDERS
    before = len(wait_unique(expected))
    podman("kill", "s3-connect")
    for n in range(ORDERS + 1, ORDERS + LATE_ORDERS + 1):
        with con.transaction():
            service.place_order(con, f"O-{n:04d}", f"U-{n % CUSTOMERS + 1:04d}", 20 + n)
        with con.transaction():
            service.advance_order(con, f"O-{n:04d}")
    expected += LATE_ORDERS * 2
    podman("start", "s3-connect")
    wait_unique(expected)
    after = wait_stable()
    store.set_fact(con, "restart_messages_before_kill", before)
    store.set_fact(con, "restart_written_while_down", LATE_ORDERS * 2)
    store.set_fact(con, "restart_messages_after", len(after))
    store.set_fact(con, "restart_unique_after", unique(after))
    log(f"connect killed and started: {before} messages before, {LATE_ORDERS * 2} events written while down, {len(after)} messages after, {unique(after)} unique, {len(after) - unique(after)} redelivered")
    return expected


def crashed(con, expected):
    for variant in VARIANTS:
        first = 1
        for stop in CRASH_AT + [0]:
            code = subprocess.run([sys.executable, os.path.join(APP, "worker.py"), variant, str(first), str(CRASH_ORDERS), str(stop)]).returncode
            if code != (-9 if stop else 0):
                raise SystemExit(f"{variant} worker exited with {code}")
            first = stop + 1
    store.set_fact(con, "crash_attempts", CRASH_ORDERS)
    store.set_fact(con, "crash_count", len(CRASH_AT))
    expected += CRASH_ORDERS - len(CRASH_AT)
    wait_unique(expected)
    wait_stable()
    log(f"crash contrast: {CRASH_ORDERS} orders per variant, process killed {len(CRASH_AT)} times between the two steps")
    return expected


def consume(con, name):
    delivered = consumer.consume(con)
    processed = store.scalar(con, "SELECT count(*) FROM processed_events")
    store.set_fact(con, f"consumer_{name}_delivered", delivered)
    store.set_fact(con, f"consumer_{name}_processed", processed)
    log(f"dedup consumer {name}: {delivered} messages delivered, {processed} events processed in total")


def main():
    con = store.db()
    expected = committed(con)
    rolled_back(con)
    consume(con, "1_before_restart")
    expected = deleted(con, expected)
    expected = restarted(con, expected)
    consume(con, "2_after_restart")
    expected = crashed(con, expected)
    consume(con, "3_final")
    log(f"scenarios done: {expected} committed transactions")


if __name__ == "__main__":
    main()
