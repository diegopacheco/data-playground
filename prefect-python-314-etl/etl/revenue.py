import csv
from decimal import Decimal, InvalidOperation


def read_orders(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def clean(rows):
    seen = set()
    out = []
    for row in rows:
        order_id = (row.get("order_id") or "").strip()
        category = (row.get("category") or "").strip().lower()
        try:
            quantity = int((row.get("quantity") or "").strip())
            price = Decimal((row.get("price") or "").strip())
        except (ValueError, InvalidOperation):
            continue
        if not order_id or not category or order_id in seen or quantity <= 0 or price < 0:
            continue
        seen.add(order_id)
        out.append({"order_id": order_id, "category": category, "quantity": quantity, "price": price})
    return out


def aggregate(rows):
    totals = {}
    for row in rows:
        orders, units, revenue = totals.get(row["category"], (0, 0, Decimal("0")))
        totals[row["category"]] = (orders + 1, units + row["quantity"], revenue + row["quantity"] * row["price"])
    return [
        {"category": c, "orders": o, "units": u, "revenue": str(r.quantize(Decimal("0.01")))}
        for c, (o, u, r) in sorted(totals.items())
    ]
