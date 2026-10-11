import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT = Path("/data/incoming")
COLUMNS = ["order_id", "customer_id", "order_ts", "region", "product", "quantity", "unit_price", "currency"]
REGIONS = ["NORTH", "SOUTH", "EAST", "WEST"]
PRODUCTS = {"keyboard": 49.90, "mouse": 19.50, "monitor": 219.00, "laptop": 1299.00, "headset": 89.90, "webcam": 64.00, "dock": 159.00, "cable": 9.99}
rng = random.Random(2026)
next_id = [1]


def orders(day, count):
    rows = []
    for _ in range(count):
        product = rng.choice(list(PRODUCTS))
        ts = datetime.fromisoformat(day) + timedelta(seconds=rng.randrange(0, 86400))
        rows.append({
            "order_id": f"ORD-{next_id[0]:06d}",
            "customer_id": f"C-{rng.randrange(1, 800):04d}",
            "order_ts": ts.isoformat(),
            "region": rng.choice(REGIONS),
            "product": product,
            "quantity": str(rng.randint(1, 10)),
            "unit_price": f"{PRODUCTS[product]:.2f}",
            "currency": "USD",
        })
        next_id[0] += 1
    return rows


def spoil(rows):
    picks = iter(rng.sample(range(len(rows)), 30))
    for _ in range(4):
        rows[next(picks)]["customer_id"] = ""
    for _ in range(2):
        rows[next(picks)]["order_ts"] = ""
    for _ in range(3):
        rows[next(picks)]["order_id"] = rows[next(picks)]["order_id"]
    for value in ["0", "0", "250", "999"]:
        rows[next(picks)]["quantity"] = value
    for _ in range(2):
        rows[next(picks)]["unit_price"] = "-5.00"
    for _ in range(2):
        rows[next(picks)]["region"] = "MARS"
    rows[next(picks)]["currency"] = "EUR"
    return rows


def drift(rows):
    for i, row in enumerate(rows):
        row["price"] = row.pop("unit_price")
        row["coupon_code"] = f"CPN{i % 7}" if i % 3 == 0 else ""
    return rows


def write(name, rows):
    with open(OUT / f"{name}.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    batches = [
        ("batch-001", orders("2026-09-20", 200), "2026-09-21T01:00:00"),
        ("batch-002", orders("2026-09-21", 200), "2026-09-22T01:00:00"),
        ("batch-003", spoil(orders("2026-09-18", 200)), "2026-09-22T01:30:00"),
        ("batch-004", drift(orders("2026-09-22", 150)), "2026-09-23T01:00:00"),
    ]
    manifest = []
    for name, rows, extracted_at in batches:
        write(name, rows)
        manifest.append({"batch_id": name, "file": f"{name}.csv", "extracted_at": extracted_at})
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(batches)} batches to {OUT}")


if __name__ == "__main__":
    main()
