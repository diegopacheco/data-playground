import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import data


def region_totals(seed, rows, big_cents):
    totals = {}
    for o in data.orders(seed, rows):
        t = totals.setdefault(o["region"], {"orders": 0, "cents": 0, "max_cents": 0, "big_orders": 0, "days": set()})
        t["orders"] += 1
        t["cents"] += o["cents"]
        if o["cents"] > t["max_cents"]:
            t["max_cents"] = o["cents"]
        if o["cents"] >= big_cents:
            t["big_orders"] += 1
        t["days"].add(o["day"])
    return {r: dict(t, days=len(t["days"])) for r, t in totals.items()}
