import json
import os
import statistics
import unittest
import urllib.request
from pathlib import Path
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pyspark.sql import SparkSession

DATA = os.environ.get("DATA_DIR", "/data")
RESULTS = Path(os.environ.get("RESULTS", "/app/results/results.json"))
UI = os.environ.get("UI_URL", "http://localhost:8080")
URLS = {"spark": os.environ.get("SPARK_URL", "sc://r2-spark:15002"), "sail": os.environ.get("SAIL_URL", "sc://r2-sail:50051")}
EXPECTED_ROWS = int(os.environ.get("ROWS", "5000000"))


def order_files(columns, filters=None):
    for path in sorted(Path(DATA, "orders").glob("*.parquet")):
        table = pq.read_table(path, columns=columns, filters=filters)
        yield table.append_column("revenue", pc.multiply(table["quantity"].cast(pa.int64()), table["price_cents"])) if "quantity" in columns else table


def add(totals, table, key, columns):
    grouped = table.group_by(key).aggregate([(c, "sum" if c != "order_id" else "count") for c in columns])
    names = [f"{c}_{'sum' if c != 'order_id' else 'count'}" for c in columns]
    for k, *values in zip(grouped[key].to_pylist(), *(grouped[n].to_pylist() for n in names)):
        totals[k] = [a + b for a, b in zip(totals.get(k, [0] * len(values)), values)]


def recompute():
    by_status, by_customer, rows = {}, {}, 0
    for table in order_files(["order_id", "customer_id", "status", "quantity", "price_cents"]):
        rows += table.num_rows
        add(by_status, table, "status", ["order_id", "quantity", "revenue"])
        add(by_customer, table.filter(pc.equal(table["status"], "completed")), "customer_id", ["revenue", "order_id"])
    return rows, by_status, by_customer


class BenchmarkResults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(RESULTS.read_text())
        cls.queries = {q["id"]: q for q in cls.report["queries"]}
        cls.rows_read, cls.by_status, cls.by_customer = recompute()

    def rows(self, qid, engine):
        r = self.queries[qid]["engines"][engine]
        self.assertTrue(r["supported"], f"{qid} failed on {engine}: {r.get('error')}")
        return r["rows"]

    def test_both_engines_scanned_every_generated_row(self):
        self.assertEqual(self.rows_read, EXPECTED_ROWS)
        for engine, info in self.report["engines"].items():
            self.assertEqual(info["orders_rows"], EXPECTED_ROWS, f"{engine} did not see the full dataset, timings would be for less data")

    def test_status_aggregate_matches_an_independent_pyarrow_recompute(self):
        expected = sorted([status, *totals] for status, totals in self.by_status.items())
        for engine in URLS:
            self.assertEqual(self.rows("q1", engine), expected, f"{engine} q1 disagrees with pyarrow, equality between engines alone would not catch a shared bug")

    def test_top_customers_match_an_independent_pyarrow_recompute(self):
        ranked = sorted(self.by_customer.items(), key=lambda item: (-item[1][0], item[0]))
        expected = [[customer, *totals] for customer, totals in ranked[:10]]
        for engine in URLS:
            self.assertEqual(self.rows("q2", engine), expected)

    def test_rollup_grand_total_is_the_whole_revenue(self):
        total = sum(totals[2] for totals in self.by_status.values())
        for engine in URLS:
            rows = self.rows("q7", engine)
            grand = [r for r in rows if r[0] is None and r[1] is None]
            self.assertEqual(grand, [[None, None, EXPECTED_ROWS, total]])
            for region in {r[0] for r in rows if r[0] is not None}:
                subtotal = next(r for r in rows if r[0] == region and r[1] is None)
                channels = [r for r in rows if r[0] == region and r[1] is not None]
                self.assertEqual(subtotal[3], sum(r[3] for r in channels), f"{engine} rollup subtotal for {region} is not the sum of its channels")

    def test_running_total_accumulates_and_lag_points_to_previous_month(self):
        for engine in URLS:
            running, previous, channel = 0, None, None
            for ch, _, _, revenue, run, prev in self.rows("q5", engine):
                if ch != channel:
                    running, previous, channel = 0, None, ch
                running += revenue
                self.assertEqual(run, running, f"{engine} running total broken for {ch}")
                self.assertEqual(prev, previous, f"{engine} lag broken for {ch}")
                previous = revenue

    def test_row_number_window_keeps_three_best_products_per_region(self):
        for engine in URLS:
            rows = self.rows("q4", engine)
            regions = sorted({r[0] for r in rows})
            self.assertEqual(len(rows), 3 * len(regions))
            for region in regions:
                ranked = [r for r in rows if r[0] == region]
                self.assertEqual([r[1] for r in ranked], [1, 2, 3])
                self.assertEqual([r[3] for r in ranked], sorted((r[3] for r in ranked), reverse=True))

    def test_identical_flag_is_true_only_when_rows_and_columns_match(self):
        for q in self.report["queries"]:
            spark, sail = q["engines"]["spark"], q["engines"]["sail"]
            if spark["supported"] and sail["supported"]:
                self.assertEqual(q["identical"], spark["rows"] == sail["rows"] and spark["columns"] == sail["columns"], q["id"])
                self.assertTrue(q["identical"], f"{q['id']} differs between engines")
            else:
                self.assertIsNone(q["identical"], f"{q['id']} cannot be called identical when an engine failed")

    def test_unsupported_queries_show_the_error_and_never_a_timing(self):
        for q in self.report["queries"]:
            for engine, r in q["engines"].items():
                if not r["supported"]:
                    self.assertTrue(r["error"], f"{q['id']} on {engine} failed without a reason")
                    self.assertNotIn("warm_median_ms", r)
                    self.assertIsNone(q["speedup"])

    def test_speedup_is_spark_warm_median_over_sail_warm_median(self):
        for q in self.report["queries"]:
            if q["speedup"] is not None:
                ratio = q["engines"]["spark"]["warm_median_ms"] / q["engines"]["sail"]["warm_median_ms"]
                self.assertAlmostEqual(q["speedup"], ratio, delta=0.01)

    def test_warm_median_is_the_median_of_the_recorded_runs(self):
        for q in self.report["queries"]:
            for r in q["engines"].values():
                if r["supported"]:
                    self.assertEqual(len(r["warm_ms"]), self.report["warm_runs"])
                    self.assertEqual(r["warm_median_ms"], round(statistics.median(r["warm_ms"]), 1))


class LiveEngines(unittest.TestCase):
    def test_same_client_code_gets_the_same_answer_from_both_live_servers(self):
        expected = len({c for t in order_files(["customer_id"], [("region", "=", "west"), ("channel", "=", "mobile")]) for c in t["customer_id"].to_pylist()})
        for engine, url in URLS.items():
            spark = SparkSession.builder.remote(url).getOrCreate()
            try:
                df = spark.read.parquet(f"{DATA}/orders").where("region = 'west' AND channel = 'mobile'")
                got = df.select("customer_id").distinct().count()
            finally:
                spark.stop()
            self.assertEqual(got, expected, f"{engine} at {url} returned a different distinct count")


class Ui(unittest.TestCase):
    def test_ui_serves_the_same_results_the_benchmark_wrote(self):
        with urllib.request.urlopen(f"{UI}/api/results") as r:
            served = json.load(r)
        written = json.loads(RESULTS.read_text())
        self.assertEqual(served["queries"], written["queries"])
        self.assertTrue(served["spark_ui"].startswith("http://"))

    def test_ui_page_has_every_tab(self):
        with urllib.request.urlopen(UI) as r:
            html = r.read().decode()
        for tab in ["Benchmark", "Queries", "Setup"]:
            self.assertIn(f">{tab}</button>", html)


if __name__ == "__main__":
    unittest.main()
