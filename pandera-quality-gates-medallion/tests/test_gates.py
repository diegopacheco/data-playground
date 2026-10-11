import csv
import io
import json
import os
import re
import unittest
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

UI = os.environ.get("UI_URL", "http://localhost:8080")
INCOMING = Path(os.environ.get("INCOMING", "/data/incoming"))
CONTRACT_COLUMNS = ["order_id", "customer_id", "order_ts", "region", "product", "quantity", "unit_price", "currency"]
REGIONS = {"NORTH", "SOUTH", "EAST", "WEST"}


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else (b"" if path.endswith("/run") else None)
    req = urllib.request.Request(UI + path, data=data, method="POST" if data is not None else "GET", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        with e:
            return e.code, json.loads(e.read())


def manifest():
    return json.loads((INCOMING / "manifest.json").read_text())


def read_batch(entry):
    with open(INCOMING / entry["file"], newline="") as f:
        reader = csv.DictReader(f)
        return reader.fieldnames, list(reader)


def expected_row_failures(rows):
    ids = Counter(r["order_id"] for r in rows)
    rules = {
        ("order_id", "field_uniqueness"): lambda r: ids[r["order_id"]] > 1,
        ("customer_id", "not_nullable"): lambda r: r["customer_id"] == "",
        ("order_ts", "not_nullable"): lambda r: r["order_ts"] == "",
        ("quantity", "in_range(1, 100)"): lambda r: not 1 <= int(r["quantity"]) <= 100,
        ("unit_price", "in_range(0.01, 10000)"): lambda r: not Decimal("0.01") <= Decimal(r["unit_price"]) <= 10000,
        ("region", "isin(['NORTH', 'SOUTH', 'EAST', 'WEST'])"): lambda r: r["region"] not in REGIONS,
        ("currency", "isin(['USD'])"): lambda r: r["currency"] != "USD",
    }
    return {key: {i for i, r in enumerate(rows, 1) if rule(r)} for key, rule in rules.items()}


def is_stale(rows, extracted_at):
    newest = max(datetime.fromisoformat(r["order_ts"]) for r in rows if r["order_ts"])
    return datetime.fromisoformat(extracted_at) - newest > timedelta(hours=24)


def batch_is_clean(header, rows, extracted_at):
    return header == CONTRACT_COLUMNS and not any(expected_row_failures(rows).values()) and not is_stale(rows, extracted_at)


def gold_from(rows_list):
    gold = defaultdict(lambda: [0, 0, Decimal(0)])
    for rows in rows_list:
        for r in rows:
            g = gold[(r["order_ts"][:10], r["region"])]
            g[0] += 1
            g[1] += int(r["quantity"])
            g[2] += int(r["quantity"]) * Decimal(r["unit_price"])
    return {k: (v[0], v[1], v[2].quantize(Decimal("0.01"))) for k, v in gold.items()}


def failed(report, gate):
    return {(c["column"], c["check"]): c for g in report["gates"] if g["gate"] == gate for c in g["checks"] if c["passed"] is False}


def to_csv(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CONTRACT_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


class PipelineRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        status, cls.summary = call("/api/pipeline/run")
        assert status == 200, cls.summary
        cls.batches = {e["batch_id"]: (e, *read_batch(e)) for e in manifest()}
        cls.reports = {r["batch_id"]: r for r in call("/api/batches")[1]}

    def good_ids(self):
        return [b for b, (e, h, rows) in self.batches.items() if batch_is_clean(h, rows, e["extracted_at"])]

    def test_only_batches_that_meet_every_rule_are_promoted(self):
        self.assertEqual(self.good_ids(), ["batch-001", "batch-002"], "the generated inputs no longer have 2 clean batches")
        for batch_id, report in self.reports.items():
            expected = "promoted" if batch_id in self.good_ids() else "quarantined"
            self.assertEqual(report["status"], expected, f"{batch_id} {report['failed_checks']}")
            self.assertEqual(report["failed_checks"] == [], expected == "promoted")

    def test_silver_holds_exactly_the_rows_of_promoted_batches(self):
        expected = sorted(r["order_id"] for b in self.good_ids() for r in self.batches[b][2])
        silver = call("/api/layers/silver?limit=100000")[1]
        col = silver["columns"].index("order_id")
        self.assertEqual(sorted(r[col] for r in silver["rows"]), expected)
        batch_col = silver["columns"].index("batch_id")
        self.assertEqual({r[batch_col] for r in silver["rows"]}, set(self.good_ids()), "a quarantined batch leaked into silver")

    def test_bronze_lands_every_row_of_every_batch_before_any_gate(self):
        total = sum(len(rows) for _, _, rows in self.batches.values())
        self.assertEqual(self.summary["layers"]["bronze"], total)

    def test_quarantine_holds_every_row_of_every_blocked_batch(self):
        blocked = [b for b in self.batches if b not in self.good_ids()]
        q = call("/api/layers/quarantine?limit=100000")[1]
        got = Counter(r[q["columns"].index("batch_id")] for r in q["rows"])
        self.assertEqual(dict(got), {b: len(self.batches[b][2]) for b in blocked})

    def test_bad_batch_report_names_exactly_the_rows_that_break_each_rule(self):
        entry, header, rows = self.batches["batch-003"]
        report = self.reports["batch-003"]
        self.assertEqual(report["blocked_at"], "silver")
        fails = failed(report, "silver")
        for key, expected_rows in expected_row_failures(rows).items():
            if expected_rows:
                self.assertIn(key, fails, f"{key} broke on rows {sorted(expected_rows)} but the gate did not flag it")
                self.assertEqual(set(fails[key]["rows"]), expected_rows, key)
            else:
                self.assertNotIn(key, fails)
        self.assertTrue(is_stale(rows, entry["extracted_at"]))
        self.assertIn(("*", "freshness: newest order within 24h of extraction"), fails)

    def test_quarantined_rows_carry_the_checks_that_failed_on_them(self):
        _, _, rows = self.batches["batch-003"]
        q = call("/api/layers/quarantine?limit=100000")[1]
        cols = q["columns"]
        by_row = {r[cols.index("row_num")]: json.loads(r[cols.index("failed_checks")]) for r in q["rows"] if r[cols.index("batch_id")] == "batch-003"}
        for (column, check), expected_rows in expected_row_failures(rows).items():
            for i in expected_rows:
                self.assertTrue(any(f.startswith(f"silver | {column}:") for f in by_row[i]), f"row {i} misses its {column} failure")
        self.assertTrue(all(any("freshness" in f for f in checks) for checks in by_row.values()), "a stale batch blocks every row")

    def test_schema_drift_is_blocked_at_bronze_with_missing_and_extra_columns(self):
        _, header, _ = self.batches["batch-004"]
        report = self.reports["batch-004"]
        self.assertEqual(report["blocked_at"], "bronze")
        fails = failed(report, "bronze")
        self.assertEqual(set(fails[("*", "column_in_dataframe")]["samples"]), set(CONTRACT_COLUMNS) - set(header))
        self.assertEqual(set(fails[("*", "column_in_schema")]["samples"]), set(header) - set(CONTRACT_COLUMNS))
        self.assertTrue(all(g["skipped"] for g in report["gates"] if g["gate"] != "bronze"), "later gates must not run on a drifted schema")

    def test_gold_equals_an_independent_aggregate_of_promoted_batches(self):
        expected = gold_from(self.batches[b][2] for b in self.good_ids())
        gold = call("/api/layers/gold?limit=1000")[1]
        got = {(r[0], r[1]): (r[2], r[3], Decimal(str(r[4])).quantize(Decimal("0.01"))) for r in gold["rows"]}
        self.assertEqual(gold["columns"], ["day", "region", "orders", "units", "revenue"])
        self.assertEqual(got, expected)

    def test_ui_serves_every_tab(self):
        with urllib.request.urlopen(UI + "/", timeout=10) as r:
            html = r.read().decode()
        for tab in ["pipeline", "reports", "contracts", "layers", "submit"]:
            self.assertIn(f'data-tab="{tab}"', html)


class LiveGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        call("/api/pipeline/run")
        entry = manifest()[0]
        cls.extracted_at = entry["extracted_at"]
        cls.rows = read_batch(entry)[1]

    @classmethod
    def tearDownClass(cls):
        call("/api/pipeline/run")

    def fresh_rows(self, start):
        rows = [dict(r) for r in self.rows[:20]]
        for i, r in enumerate(rows):
            r["order_id"] = f"ORD-{start + i:06d}"
        return rows

    def gold_revenue(self):
        return Decimal(str(call("/api/summary")[1]["gold_revenue"]))

    def silver_count(self):
        return call("/api/summary")[1]["layers"]["silver"]

    def test_a_new_clean_batch_is_promoted_and_gold_grows_by_its_revenue(self):
        rows = self.fresh_rows(900000)
        before = self.gold_revenue()
        status, report = call("/api/batches", {"batch_id": "live-clean", "extracted_at": self.extracted_at, "csv": to_csv(rows)})
        self.assertEqual(status, 201)
        self.assertEqual(report["status"], "promoted", report["failed_checks"])
        added = sum(int(r["quantity"]) * Decimal(r["unit_price"]) for r in rows)
        self.assertEqual(self.gold_revenue() - before, added)

    def test_one_null_and_one_out_of_range_value_block_the_whole_batch(self):
        rows = self.fresh_rows(910000)
        rows[3]["customer_id"] = ""
        rows[7]["quantity"] = "101"
        silver, revenue = self.silver_count(), self.gold_revenue()
        _, report = call("/api/batches", {"batch_id": "live-bad", "extracted_at": self.extracted_at, "csv": to_csv(rows)})
        self.assertEqual(report["status"], "quarantined")
        fails = failed(report, "silver")
        self.assertEqual(set(fails), {("customer_id", "not_nullable"), ("quantity", "in_range(1, 100)")})
        self.assertEqual(fails[("customer_id", "not_nullable")]["rows"], [4])
        self.assertEqual(fails[("quantity", "in_range(1, 100)")]["rows"], [8])
        self.assertEqual((self.silver_count(), self.gold_revenue()), (silver, revenue), "a blocked batch changed silver or gold")

    def test_replaying_already_promoted_orders_is_blocked(self):
        rows = [dict(r) for r in self.rows[:5]]
        _, report = call("/api/batches", {"batch_id": "live-replay", "extracted_at": self.extracted_at, "csv": to_csv(rows)})
        self.assertEqual(report["status"], "quarantined")
        self.assertEqual(failed(report, "silver")[("order_id", "order_id not already promoted")]["rows"], [1, 2, 3, 4, 5])

    def test_an_order_after_the_extraction_time_and_a_stale_batch_are_blocked(self):
        rows = self.fresh_rows(920000)
        rows[0]["order_ts"] = "2026-09-21T05:00:00"
        _, future = call("/api/batches", {"batch_id": "live-future", "extracted_at": self.extracted_at, "csv": to_csv(rows)})
        self.assertEqual(set(failed(future, "silver")), {("order_ts", "order_ts not after extraction")})
        late = (datetime.fromisoformat(self.extracted_at) + timedelta(hours=30)).isoformat()
        _, stale = call("/api/batches", {"batch_id": "live-stale", "extracted_at": late, "csv": to_csv(self.fresh_rows(930000))})
        self.assertEqual(set(failed(stale, "silver")), {("*", "freshness: newest order within 24h of extraction")})

    def test_a_reused_batch_id_is_rejected(self):
        status, body = call("/api/batches", {"batch_id": "batch-001", "extracted_at": self.extracted_at, "csv": to_csv(self.fresh_rows(940000))})
        self.assertEqual(status, 409)
        self.assertTrue(re.search("already processed", body["error"]))
