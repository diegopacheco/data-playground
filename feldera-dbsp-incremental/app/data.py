from datetime import datetime, timedelta

REGIONS = ["us", "eu", "br", "jp", "in"]
BASE = datetime(2026, 1, 1)
HOURS = 48


def order(i):
    return {
        "id": i,
        "customer": (i * 7919) % 1000,
        "region": REGIONS[(i * 31 + i // 7) % len(REGIONS)],
        "amount": (i * 2654435761) % 10000 + 1,
        "ts": (BASE + timedelta(seconds=(i * 48271) % (HOURS * 3600))).strftime("%Y-%m-%d %H:%M:%S"),
    }


def orders(start, stop):
    return [order(i) for i in range(start, stop)]


def csv_rows(rows):
    return "".join(f"{r['id']},{r['customer']},{r['region']},{r['amount']},{r['ts']}\n" for r in rows)


GRAPH = [(1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 3), (7, 8), (8, 9), (2, 7), (10, 11)]
