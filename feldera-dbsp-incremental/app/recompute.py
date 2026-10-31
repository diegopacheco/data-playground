import itertools
import os
import tempfile
from collections import Counter
import duckdb
import data

DUCK_TOTALS = "SELECT region, COUNT(*) AS orders, SUM(amount) AS revenue FROM orders GROUP BY region"
DUCK_HOURLY = "SELECT strftime(date_trunc('hour', ts), '%Y-%m-%dT%H:%M:%S') AS window_start, region, COUNT(*) AS orders, SUM(amount) AS revenue FROM orders GROUP BY ALL"
AMOUNT = 100_000


def normalize(rows):
    if rows and "window_start" in rows[0]:
        return sorted((r["window_start"], r["region"], int(r["orders"]), int(r["revenue"])) for r in rows)
    return sorted((r["region"], int(r["orders"]), int(r["revenue"])) for r in rows)


class State:
    def __init__(self):
        self.rows = {}
        self.deleted = set()
        self.groups = []
        self.group_ids = {}
        self.db = duckdb.connect()
        self.db.execute("SET threads TO 2")
        self.db.execute("CREATE TABLE orders (id BIGINT PRIMARY KEY, customer INTEGER, region VARCHAR, amount BIGINT, ts TIMESTAMP)")
        self.csv = os.path.join(tempfile.mkdtemp(), "rows.csv")

    def group(self, row):
        key = (row["ts"][:13].replace(" ", "T") + ":00:00", row["region"])
        if key not in self.group_ids:
            self.group_ids[key] = len(self.groups)
            self.groups.append(key)
        return self.group_ids[key]

    def load(self, rows):
        for r in rows:
            self.rows[r["id"]] = self.group(r) * AMOUNT + r["amount"]
        with open(self.csv, "w") as f:
            f.write(data.csv_rows(rows))
        self.db.execute(f"INSERT INTO orders SELECT * FROM read_csv('{self.csv}', header=false, columns={{'id':'BIGINT','customer':'INTEGER','region':'VARCHAR','amount':'BIGINT','ts':'TIMESTAMP'}})")

    def apply(self, victims, rows):
        for i in victims:
            del self.rows[i]
        self.deleted.update(victims)
        if victims:
            self.db.execute(f"DELETE FROM orders WHERE id IN ({','.join(map(str, victims))})")
        if rows:
            self.load(rows)

    def oldest(self, n):
        return list(itertools.islice(iter(self.rows), n))

    def count(self):
        return len(self.rows)

    def duckdb_views(self):
        totals = self.db.execute(DUCK_TOTALS).fetchall()
        hourly = self.db.execute(DUCK_HOURLY).fetchall()
        return sorted((r, int(c), int(s)) for r, c, s in totals), sorted((w, r, int(c), int(s)) for w, r, c, s in hourly)

    def python_views(self):
        counts = Counter()
        sums = Counter()
        for packed in self.rows.values():
            g, amount = divmod(packed, AMOUNT)
            counts[g] += 1
            sums[g] += amount
        totals = Counter()
        revenue = Counter()
        for g, c in counts.items():
            totals[self.groups[g][1]] += c
            revenue[self.groups[g][1]] += sums[g]
        hourly = sorted((self.groups[g][0], self.groups[g][1], c, sums[g]) for g, c in counts.items())
        return sorted((r, c, revenue[r]) for r, c in totals.items()), hourly
