import csv
import json
import os
import unittest
import urllib.error
import urllib.request
from collections import defaultdict
from decimal import Decimal

import s3

UI = os.environ.get("UI_URL", "http://localhost:27603")
DATA = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
BUCKET = "lake"


def call(path, method="GET"):
    req = urllib.request.Request(UI + path, method=method)
    with urllib.request.urlopen(req, timeout=120) as res:
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
        return list(csv.DictReader(f))


def money(v):
    return Decimal(str(v)).quantize(Decimal("0.01"))


def revenue(o):
    return int(o["quantity"]) * Decimal(o["price"])


CUSTOMERS = {int(c["customer_id"]): c for c in read_csv("customers.csv")}
BATCH1 = read_csv("orders-batch-1.csv")
BATCH2 = read_csv("orders-batch-2.csv")
ALL = BATCH1 + BATCH2
KEPT = [o for o in ALL if o["status"] != "cancelled"]


def expected_by_country(orders):
    out = defaultdict(lambda: [0, 0, Decimal("0")])
    for o in orders:
        c = out[CUSTOMERS[int(o["customer_id"])]["country"]]
        c[0] += 1
        c[1] += int(o["quantity"])
        c[2] += revenue(o)
    return {k: (v[0], v[1], money(v[2])) for k, v in out.items()}


def expected_monthly(orders):
    out = defaultdict(lambda: [0, Decimal("0")])
    for o in orders:
        m = out[(o["order_date"][:7], o["status"])]
        m[0] += 1
        m[1] += revenue(o)
    return {k: (v[0], money(v[1])) for k, v in out.items()}


def table(name):
    return next(t for t in call("/api/status")["tables"] if t["name"] == name)


class LakehouseTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        reset = call("/api/reset", "POST")
        assert reset["customers"] == len(CUSTOMERS), reset
        cls.load1 = call("/api/load?batch=1", "POST")
        cls.after1 = table("orders")["rows"]
        cls.lake1 = call("/api/lake")
        cls.load2 = call("/api/load?batch=2", "POST")
        cls.after2 = table("orders")["rows"]
        cls.deleted = call("/api/delete-cancelled", "POST")
        cls.lake = call("/api/lake")

    def test_1_every_csv_row_reaches_the_iceberg_table_batch_by_batch(self):
        self.assertEqual(self.load1["inserted"], len(BATCH1))
        self.assertEqual(self.after1, len(BATCH1))
        self.assertEqual(self.load2["inserted"], len(BATCH2))
        self.assertEqual(self.after2, len(ALL))

    def test_2_delete_on_iceberg_removes_exactly_the_cancelled_orders(self):
        cancelled = len(ALL) - len(KEPT)
        self.assertGreater(cancelled, 0)
        self.assertEqual(self.deleted["deleted"], cancelled)
        self.assertEqual(table("orders")["rows"], len(KEPT))

    def test_3_parquet_files_written_by_postgres_read_back_equal_to_the_csv(self):
        raw = call("/api/query/raw")
        got = {r["file"].rsplit("/", 1)[1]: (r["orders"], money(r["revenue"])) for r in raw["rows"]}
        self.assertEqual(got, {
            "batch-1.parquet": (len(BATCH1), money(sum(revenue(o) for o in BATCH1))),
            "batch-2.parquet": (len(BATCH2), money(sum(revenue(o) for o in BATCH2))),
        })

    def test_4_join_of_iceberg_orders_with_heap_customers_matches_the_csv(self):
        result = call("/api/query/revenue")
        got = {r["country"]: (r["orders"], r["units"], money(r["revenue"])) for r in result["rows"]}
        self.assertEqual(got, expected_by_country(KEPT))
        self.assertEqual(table("customers")["storage"], "heap")
        self.assertEqual(table("orders")["storage"], "pg_lake_iceberg")
        self.assertIn("Engine: DuckDB", result["plan"], "the iceberg side of the join must run in duckdb")
        self.assertIn("customers", result["plan"])

    def test_5_lake_only_aggregate_is_fully_pushed_down_to_duckdb(self):
        result = call("/api/query/monthly")
        got = {(r["month"], r["status"]): (r["orders"], money(r["revenue"])) for r in result["rows"]}
        self.assertEqual(got, expected_monthly(KEPT))
        self.assertTrue(result["pushdown"], result["plan"])

    def test_6_month_partitioning_prunes_data_files(self):
        result = call("/api/query/august")
        self.assertEqual(result["rows"][0]["orders"], sum(1 for o in KEPT if o["order_date"] >= "2026-08-01"))
        self.assertIn("Data Files Scanned: 1\n", result["plan"], "only the august data file may be read")
        self.assertIn("Data Files Scanned: 2\n", call("/api/query/revenue")["plan"])
        spec = self.lake["partitionSpecs"][-1]["fields"]
        self.assertEqual([f["transform"] for f in spec], ["month"])
        data = sorted(f["record_count"] for f in self.lake["files"] if f["content"] == "DATA")
        self.assertEqual(data, sorted([len(BATCH1), len(BATCH2)]), "one data file per month partition")

    def test_7_every_iceberg_file_is_really_in_minio(self):
        objects = {f"s3://{BUCKET}/{o['key']}": o["size"] for o in s3.list_objects(BUCKET)}
        self.assertIn(f"s3://{BUCKET}/raw/orders/batch-1.parquet", objects)
        self.assertIn(f"s3://{BUCKET}/raw/orders/batch-2.parquet", objects)
        self.assertTrue(self.lake["files"])
        for f in self.lake["files"]:
            self.assertEqual(objects.get(f["file_path"]), f["file_size_in_bytes"], f["file_path"])
        location = next(t["metadata_location"] for t in self.lake["tables"] if t["table_name"] == "orders")
        self.assertIn(location, objects)

    def test_8_metadata_json_in_minio_records_one_snapshot_per_write(self):
        location = next(t["metadata_location"] for t in self.lake["tables"] if t["table_name"] == "orders")
        meta = json.loads(s3.get_object(BUCKET, location.split(f"s3://{BUCKET}/", 1)[1]))
        ops = [s["summary"]["operation"] for s in sorted(meta["snapshots"], key=lambda s: s["sequence-number"])]
        self.assertEqual(ops, ["append", "append", "delete"])
        self.assertEqual(meta["current-snapshot-id"], max(meta["snapshots"], key=lambda s: s["sequence-number"])["snapshot-id"])
        data = sum(f["record_count"] for f in self.lake["files"] if f["content"] == "DATA")
        deletes = sum(f["record_count"] for f in self.lake["files"] if f["content"] == "POSITION_DELETES")
        self.assertEqual(data, len(ALL), "delete must not rewrite data files")
        self.assertEqual(deletes, len(ALL) - len(KEPT), "one position delete per cancelled order")

    def test_9_bad_input_is_rejected(self):
        self.assertEqual(status_code("/api/load?batch=9", "POST"), 400)
        self.assertEqual(status_code("/api/load?batch=abc", "POST"), 400)
        self.assertEqual(status_code("/api/load?batch=1", "POST"), 409)
        self.assertEqual(status_code("/api/query/nope"), 404)
        self.assertEqual(table("orders")["rows"], len(KEPT))


if __name__ == "__main__":
    unittest.main()
