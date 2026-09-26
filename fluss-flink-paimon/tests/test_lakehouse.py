import csv
import json
import os
import time
import unittest
import urllib.error
import urllib.request
from decimal import Decimal

UI = os.environ.get("UI_URL", "http://localhost:26600")
FLINK = os.environ.get("FLINK_URL", "http://localhost:26601")
DATA = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


def call(path, method="GET"):
    req = urllib.request.Request(UI + path, method=method)
    with urllib.request.urlopen(req, timeout=180) as res:
        return json.load(res)


def status_code(path, method="GET"):
    try:
        call(path, method)
        return 200
    except urllib.error.HTTPError as e:
        e.close()
        return e.code


def read_csv(name):
    with open(os.path.join(DATA, name), newline="") as f:
        return {int(r["order_id"]): r for r in csv.DictReader(f)}


def categories(rows):
    out = {}
    for r in rows.values():
        c = out.setdefault(r["category"], {"orders": 0, "units": 0, "revenue": Decimal("0")})
        c["orders"] += 1
        c["units"] += int(r["quantity"])
        c["revenue"] += int(r["quantity"]) * Decimal(r["price"])
    return {k: (v["orders"], v["units"], v["revenue"].quantize(Decimal("0.01"))) for k, v in out.items()}


def api_categories(items):
    return {c["category"]: (c["orders"], c["units"], Decimal(str(c["revenue"])).quantize(Decimal("0.01"))) for c in items}


def lake_offset():
    snap = call("/api/status")["lakeSnapshot"]
    return sum(o["offset"] for o in snap["offsets"]) if snap else 0


def wait_for(predicate, tries):
    for _ in range(tries):
        if predicate():
            return True
        time.sleep(1)
    return False


BATCH1 = read_csv("orders.csv")
UPDATES = read_csv("orders-updates.csv")
MERGED = {**BATCH1, **UPDATES}
CHANGED = {k for k, v in UPDATES.items() if BATCH1.get(k) != v}


class LakehouseTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        call("/api/reset", "POST")
        ingested = call("/api/ingest?file=orders.csv", "POST")
        assert ingested["rows"] == len(BATCH1), ingested
        if not wait_for(lambda: lake_offset() >= len(BATCH1), 120):
            raise AssertionError("tiering service did not commit batch 1 to paimon within 120 s")

    def test_1_first_batch_is_the_same_in_fluss_lake_and_union(self):
        expected = categories(BATCH1)
        self.assertEqual(api_categories(call("/api/fluss")["categories"]), expected)
        lake = call("/api/lake")
        self.assertEqual(api_categories(lake["categories"]), expected)
        self.assertEqual(lake["snapshots"][0]["total"], len(BATCH1))
        union = call("/api/union")
        self.assertEqual(api_categories(union["categories"]), expected)
        self.assertEqual(union["fresh"], [], "after tiering the lake must already hold every row")

    def test_2_point_lookup_reads_the_primary_key_from_fluss(self):
        found = call("/api/lookup?id=1042")
        self.assertEqual(found["fluss"]["product"], BATCH1[1042]["product"])
        self.assertEqual(Decimal(str(found["fluss"]["price"])), Decimal(BATCH1[1042]["price"]))
        self.assertEqual(found["fluss"], found["lake"])
        missing = call("/api/lookup?id=999999")
        self.assertIsNone(missing["fluss"])
        self.assertIsNone(missing["lake"])
        self.assertEqual(status_code("/api/lookup?id=abc"), 400)
        self.assertEqual(status_code("/api/ingest?file=..%2F..%2Fetc%2Fpasswd", "POST"), 400)

    def test_3_paused_tiering_leaves_the_lake_stale_while_union_read_is_fresh(self):
        call("/api/tiering/pause", "POST")
        self.assertFalse(call("/api/status")["tiering"]["running"])
        before = lake_offset()
        call("/api/ingest?file=orders-updates.csv", "POST")

        self.assertEqual(api_categories(call("/api/fluss")["categories"]), categories(MERGED))
        moved = call("/api/lookup?id=1006")
        self.assertEqual(moved["fluss"]["category"], "sports", "fluss kv must serve the upsert right away")
        self.assertEqual(moved["lake"]["category"], "toys", "paimon must not change while tiering is paused")

        time.sleep(10)
        self.assertEqual(lake_offset(), before, "no tiering round may commit while the job is cancelled")
        self.assertEqual(api_categories(call("/api/lake")["categories"]), categories(BATCH1))
        union = call("/api/union")
        self.assertEqual(api_categories(union["categories"]), categories(MERGED))
        self.assertNotEqual(categories(MERGED), categories(BATCH1))
        self.assertEqual({f["order"]["order_id"] for f in union["fresh"]}, CHANGED)
        new_orders = {f["order"]["order_id"] for f in union["fresh"] if f["lake"] is None}
        self.assertEqual(new_orders, set(UPDATES) - set(BATCH1))

    def test_4_resumed_tiering_catches_the_lake_up(self):
        before = lake_offset()
        snapshots = len(call("/api/lake")["snapshots"])
        call("/api/tiering/resume", "POST")
        self.assertTrue(call("/api/status")["tiering"]["running"])
        self.assertTrue(wait_for(lambda: lake_offset() > before, 240), "tiering did not resume within 240 s")
        lake = call("/api/lake")
        self.assertEqual(api_categories(lake["categories"]), categories(MERGED))
        self.assertGreater(len(lake["snapshots"]), snapshots)
        self.assertEqual(call("/api/lookup?id=1006")["lake"]["category"], "sports")
        self.assertEqual(call("/api/union")["fresh"], [])

    def test_5_tiering_is_a_flink_job_visible_in_the_flink_web_ui(self):
        with urllib.request.urlopen(FLINK + "/jobs/overview", timeout=30) as res:
            jobs = json.load(res)["jobs"]
        running = [j for j in jobs if j["state"] == "RUNNING"]
        self.assertEqual([j["name"] for j in running], ["Fluss Lake Tiering Service - paimon"])
        self.assertEqual(running[0]["jid"], call("/api/status")["tiering"]["jobId"])


if __name__ == "__main__":
    unittest.main()
