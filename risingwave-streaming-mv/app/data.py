import random
from datetime import datetime, timedelta

SEED = 42
BASE_TIME = datetime(2026, 10, 1, 12, 0, 0)
MINUTES = 10
ORDER_COUNT = 120
REGIONS = ["north", "south", "east", "west"]
PRODUCTS = ["keyboard", "mouse", "monitor", "laptop", "headset", "webcam"]
NAMES = ["ana", "bruno", "carla", "diego", "elisa", "fabio", "gina", "hugo"]
MOVED_CUSTOMER = 3
MOVED_TO = "west"


def stamp(t):
    return t.strftime("%Y-%m-%d %H:%M:%S")


def make_order(rng, order_id, customer_count, first_second, last_second):
    return {
        "order_id": order_id,
        "customer_id": rng.randint(1, customer_count),
        "product": rng.choice(PRODUCTS),
        "amount_cents": rng.randint(500, 20000),
        "event_time": stamp(BASE_TIME + timedelta(seconds=rng.randint(first_second, last_second))),
        "version": 1,
    }


def make_payments(rng, orders, next_id):
    payments = []
    unpaid = []
    for order in orders:
        roll = rng.random()
        amount = order["amount_cents"]
        if roll < 0.5:
            parts = [amount]
        elif roll < 0.75:
            parts = [amount // 2, amount - amount // 2]
        elif roll < 0.85:
            parts = [amount // 3]
        else:
            unpaid.append(order)
            continue
        for part in parts:
            payments.append({
                "payment_id": next_id + len(payments),
                "order_id": order["order_id"],
                "paid_cents": part,
                "paid_at": order["event_time"],
            })
    return payments, unpaid


def build():
    rng = random.Random(SEED)
    customers = [
        {"customer_id": i + 1, "name": name, "region": REGIONS[i % len(REGIONS)]}
        for i, name in enumerate(NAMES)
    ]
    orders = [make_order(rng, i, len(customers), 0, MINUTES * 60 - 1) for i in range(1, ORDER_COUNT + 1)]
    payments, unpaid = make_payments(rng, orders, 1)
    updated = [
        dict(order, amount_cents=order["amount_cents"] + rng.randint(1000, 5000), version=2)
        for order in rng.sample(orders, 5)
    ]
    late = [make_order(rng, i, len(customers), 0, 179) for i in range(ORDER_COUNT + 1, ORDER_COUNT + 5)]
    late_payments = [
        {"payment_id": len(payments) + 1 + i, "order_id": order["order_id"],
         "paid_cents": order["amount_cents"], "paid_at": order["event_time"]}
        for i, order in enumerate(unpaid[:3])
    ]
    return {
        "customers": customers,
        "orders": orders,
        "payments": payments,
        "corrections": {
            "updated_orders": updated,
            "late_orders": late,
            "late_payments": late_payments,
            "moved_customer": {"customer_id": MOVED_CUSTOMER, "region": MOVED_TO},
        },
    }
