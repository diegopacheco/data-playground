import json

BIG_ORDER_CENTS = 10000


def parse(raw):
    try:
        order = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(order, dict):
        return None
    qty = order.get("qty")
    price = order.get("price_cents")
    if type(qty) is not int or type(price) is not int or qty <= 0 or price < 0:
        return None
    if not order.get("id"):
        return None
    return order


def enrich(order):
    total = order["qty"] * order["price_cents"]
    tier = "big" if total >= BIG_ORDER_CENTS else "small"
    return {**order, "total_cents": total, "tier": tier}


def process(raw):
    order = parse(raw)
    if order is None:
        return None
    return enrich(order)
