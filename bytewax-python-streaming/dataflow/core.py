import json
from datetime import datetime, timedelta, timezone

from bytewax import operators as op
from bytewax.operators import windowing as win
from bytewax.operators.windowing import EventClock, TumblingWindower

ALIGN = datetime(2026, 1, 1, tzinfo=timezone.utc)
WINDOW = timedelta(days=1)
FROZEN_SYSTEM_TIME = datetime(2000, 1, 1, tzinfo=timezone.utc)


def parse(raw):
    o = json.loads(raw)
    quantity = int(o["quantity"])
    return {
        "order_id": int(o["order_id"]),
        "category": o["category"],
        "quantity": quantity,
        "revenue_cents": round(quantity * float(o["price"]) * 100),
        "ts": datetime.fromisoformat(o["ts"].replace("Z", "+00:00")),
    }


def empty():
    return {"orders": 0, "quantity": 0, "revenue_cents": 0}


def add(acc, order):
    return {
        "orders": acc["orders"] + 1,
        "quantity": acc["quantity"] + order["quantity"],
        "revenue_cents": acc["revenue_cents"] + order["revenue_cents"],
    }


def merge(a, b):
    return {k: a[k] + b[k] for k in a}


def running(state, order):
    total = add(state or empty(), order)
    return total, {**total, "last_order_id": order["order_id"]}


def window_start(window_id):
    return (ALIGN + WINDOW * window_id).isoformat().replace("+00:00", "Z")


def as_total(category_total):
    category, total = category_total
    return {"kind": "total", "category": category, **total}


def as_window(category_window):
    category, (window_id, acc) = category_window
    return {"kind": "window", "category": category, "window_start": window_start(window_id), **acc}


def aggregate(raw_stream):
    orders = op.map("parse", raw_stream, parse)
    keyed = op.key_on("key_by_category", orders, lambda o: o["category"])
    totals = op.stateful_map("running_totals", keyed, running)
    clock = EventClock(
        ts_getter=lambda o: o["ts"],
        wait_for_system_duration=timedelta(0),
        now_getter=lambda: FROZEN_SYSTEM_TIME,
    )
    windows = win.fold_window("daily_window", keyed, clock, TumblingWindower(length=WINDOW, align_to=ALIGN), empty, add, merge)
    return op.merge(
        "results",
        op.map("total_record", totals, as_total),
        op.map("window_record", windows.down, as_window),
    )
