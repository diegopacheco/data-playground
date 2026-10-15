import service
import store
import worker

ORDER_TOPIC = store.OUTBOX_TOPICS + "order"
CUSTOMER_TOPIC = store.OUTBOX_TOPICS + "customer"


def load(con):
    return {
        "events": store.read(store.OUTBOX_TOPICS),
        "dual": store.read(store.DUAL_TOPICS),
        "orders": store.rows(con, "SELECT order_id, status, version FROM orders ORDER BY version DESC, order_id"),
        "customers": [r["customer_id"] for r in store.rows(con, "SELECT customer_id FROM customers")],
        "projection": {r["aggregateid"]: r for r in store.rows(con, "SELECT * FROM projection")},
        "facts": store.facts(con),
    }


def topics(data):
    out = {}
    for e in data["events"] + data["dual"]:
        t = out.setdefault(e["topic"], {"topic": e["topic"], "messages": 0, "ids": set(), "keys": set(), "partitions": set(), "tombstones": 0})
        t["messages"] += 1
        t["ids"].add(e["id"])
        t["keys"].add(e["key"])
        t["partitions"].add(e["partition"])
        t["tombstones"] += e["value"] is None
    return [{
        "topic": t["topic"], "messages": t["messages"], "unique_events": len(t["ids"]),
        "redelivered": t["messages"] - len(t["ids"]), "keys": len(t["keys"]),
        "partitions": sorted(t["partitions"]), "tombstones": t["tombstones"],
    } for t in out.values()]


def aggregates(data):
    by_key = {}
    for e in data["events"]:
        if e["topic"] == ORDER_TOPIC:
            by_key.setdefault(e["key"], []).append(e)
    out = []
    for o in data["orders"]:
        events = by_key.get(o["order_id"], [])
        seen = set()
        sequence = [e["type"] for e in events if not (e["id"] in seen or seen.add(e["id"]))]
        view = data["projection"].get(o["order_id"], {})
        out.append({
            "order_id": o["order_id"], "status": o["status"], "version": o["version"],
            "partitions": sorted({e["partition"] for e in events}),
            "messages": len(events), "sequence": sequence,
            "ordered": sequence == service.LIFECYCLE[:o["version"]],
            "applied": view.get("applied", 0), "deliveries": view.get("deliveries", 0), "last_type": view.get("last_type"),
        })
    return out


def dualwrite(con, data):
    out = []
    for variant, prefix in worker.PREFIX.items():
        if variant == "outbox":
            stored = {o["order_id"] for o in data["orders"] if o["order_id"].startswith(prefix)}
            published = {e["key"] for e in data["events"] if e["key"].startswith(prefix)}
        else:
            stored = {r["order_id"] for r in store.rows(con, "SELECT order_id FROM dual_write_orders WHERE variant = %s", (variant,))}
            published = {e["key"] for e in data["dual"] if e["topic"] == f"{store.DUAL_TOPICS}{variant}.order"}
        out.append({
            "variant": variant, "attempts": data["facts"].get("crash_attempts", 0), "crashes": data["facts"].get("crash_count", 0),
            "rows": len(stored), "events": len(published),
            "rows_without_event": sorted(stored - published), "events_without_row": sorted(published - stored),
        })
    return out


def claim(name, detail, expected, actual):
    return {"claim": name, "detail": detail, "expected": expected, "actual": actual, "ok": expected == actual}


def proof(con, data):
    events, facts, orders = data["events"], data["facts"], data["orders"]
    order_ids = {o["order_id"] for o in orders}
    customer_ids = set(data["customers"])
    committed = len(customer_ids) + sum(o["version"] for o in orders)
    ids = {e["id"] for e in events}
    misrouted = sum(1 for e in events if not (
        (e["topic"] == ORDER_TOPIC and e["key"] in order_ids and e["type"] in service.LIFECYCLE)
        or (e["topic"] == CUSTOMER_TOPIC and e["key"] in customer_ids and e["type"] == "CustomerRegistered")))
    orders_view = aggregates(data)
    split = sum(1 for a in orders_view if len(a["partitions"]) != 1)
    unordered = sum(1 for a in orders_view if not a["ordered"])
    rolled_rows = sum(1 for o in order_ids if o.startswith("R-"))
    rolled_events = sum(1 for e in events if e["key"].startswith("R-"))
    applied = sum(v["applied"] for v in data["projection"].values())
    deliveries = sum(v["deliveries"] for v in data["projection"].values())
    drift = sum(1 for a in orders_view if a["applied"] != a["version"] or a["last_type"] != service.LIFECYCLE[a["version"] - 1])
    variants = {v["variant"]: v for v in dualwrite(con, data)}
    crashes = facts.get("crash_count", 0)
    return [
        claim("every committed transaction yields exactly one event", "customers + sum(orders.version) in postgres vs unique event ids on kafka", committed, len(ids)),
        claim("every event is on the topic of its aggregate type with the aggregate id as key", "events on the wrong topic, with an unknown key or a foreign type", 0, misrouted),
        claim("a rolled-back transaction leaves no business row", f"{facts.get('rollback_attempts', 0)} rolled-back orders R-*, rows found in orders", 0, rolled_rows),
        claim("a rolled-back transaction leaves no event", "events with key R-* on kafka", 0, rolled_events),
        claim("all events of one order stay in one partition", f"orders spread over more than one partition, out of {len(orders_view)}", 0, split),
        claim("events of one order keep their order", "orders whose event sequence differs from Placed, Paid, Shipped, Delivered up to orders.version", 0, unordered),
        claim("deleting captured outbox rows emits no event", f"{facts.get('delete_outbox_rows', 0)} rows deleted, messages before delete + 1 marker event vs messages after", facts.get("delete_messages_before", 0) + 1, facts.get("delete_messages_after", 0)),
        claim("no tombstone reaches kafka", "messages with a null value on outbox.event.*", 0, sum(1 for e in events if e["value"] is None)),
        claim("no event is lost when connect is killed and started", f"{facts.get('restart_written_while_down', 0)} events written while connect was down, committed vs unique after restart", committed, len(ids)),
        claim("the consumer saw every delivery, redeliveries included", f"{len(events) - len(ids)} messages redelivered after the restart, messages on kafka vs deliveries counted", len(events), deliveries),
        claim("deduplication on the id header applies each event once", "committed transactions vs events applied to the projection", committed, applied),
        claim("the projection equals the business tables", "orders whose applied count or last event differs from orders.version", 0, drift),
        claim("outbox under a crash keeps rows and events equal", f"{crashes} crashes, rows without event + events without row", 0, len(variants["outbox"]["rows_without_event"]) + len(variants["outbox"]["events_without_row"])),
        claim("dual write, database first, loses events", f"{crashes} crashes after the commit, rows without event", crashes, len(variants["db-first"]["rows_without_event"])),
        claim("dual write, kafka first, publishes phantom events", f"{crashes} crashes after the publish, events without row", crashes, len(variants["kafka-first"]["events_without_row"])),
    ]
