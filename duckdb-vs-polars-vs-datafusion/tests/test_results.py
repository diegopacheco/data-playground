import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "data" / "orders.csv"
REPORT = json.loads((ROOT / "results.json").read_text())
QUERIES = {q["id"]: q for q in REPORT["queries"]}
BASE_ROWS = sum(1 for _ in CSV.open()) - 1
FACTOR = REPORT["dataset_rows"] // BASE_ROWS

AWK_Q1 = 'NR>1{c[$4]++; q[$4]+=$5; r[$4]+=$5*int($6*100+0.5)} END{for(k in c) printf "%s %d %d %d\\n", k, c[k]*f, q[k]*f, r[k]*f}'
AWK_Q2 = 'NR>1{r[$2]+=$5*int($6*100+0.5)} END{for(k in r) printf "%s|%d\\n", k, r[k]*f}'


def awk(program):
    out = subprocess.run(["awk", "-F,", "-v", f"f={FACTOR}", program, str(CSV)], capture_output=True, text=True, check=True)
    return out.stdout.strip().splitlines()


class ResultsTest(unittest.TestCase):
    def test_dataset_is_the_base_orders_expanded_to_about_ten_million_rows(self):
        self.assertEqual(REPORT["dataset_rows"], BASE_ROWS * FACTOR)
        self.assertGreaterEqual(REPORT["dataset_rows"], 10_000_000)

    def test_every_engine_returns_identical_rows_for_every_query(self):
        for q in QUERIES.values():
            self.assertTrue(q["identical"], q["id"])
            self.assertEqual(set(q["engines"]), {"duckdb", "polars", "datafusion"})

    def test_q1_category_totals_match_awk_over_base_times_factor(self):
        expected = sorted(awk(AWK_Q1))
        actual = sorted(" ".join(str(v) for v in row) for row in QUERIES["q1"]["result"])
        self.assertEqual(actual, expected)

    def test_q2_top_customers_match_awk_ranking(self):
        totals = [line.split("|") for line in awk(AWK_Q2)]
        expected = sorted(((name, int(rev)) for name, rev in totals), key=lambda t: (-t[1], t[0]))[:10]
        self.assertEqual([tuple(r) for r in QUERIES["q2"]["result"]], expected)

    def test_q3_only_contains_days_inside_the_filtered_range(self):
        days = {row[0] for row in QUERIES["q3"]["result"]}
        self.assertEqual(min(days), "2026-03-01")
        self.assertEqual(max(days), "2026-05-31")
        self.assertEqual(len(days), 92)

    def test_q4_join_keeps_every_order(self):
        self.assertEqual(sum(row[1] for row in QUERIES["q4"]["result"]), REPORT["dataset_rows"])

    def test_every_timing_is_a_positive_median_of_the_warm_runs(self):
        for q in QUERIES.values():
            for e in q["engines"].values():
                self.assertEqual(len(e["warm_ms"]), REPORT["warm_runs"])
                self.assertGreater(e["warm_median_ms"], 0)
                self.assertGreaterEqual(e["peak_rss_mb"], e["base_rss_mb"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
