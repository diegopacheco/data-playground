import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from dataset import expand, load_base
from formats import VARIANTS, aggregate, label, projected_sum, row_count


class DatasetTest(unittest.TestCase):
    def setUp(self):
        self.base = load_base(ROOT / "data" / "orders.csv")

    def test_expansion_is_deterministic_so_runs_are_comparable(self):
        self.assertTrue(expand(self.base, 5000).equals(expand(self.base, 5000)))

    def test_expansion_keeps_base_category_mix(self):
        big = aggregate(expand(self.base, self.base.num_rows * 10))
        small = aggregate(self.base)
        for category, a in small.items():
            self.assertEqual(big[category]["orders"], a["orders"] * 10)

    def test_order_ids_are_unique(self):
        ids = expand(self.base, 3000).column("order_id").to_pylist()
        self.assertEqual(len(set(ids)), 3000)


class RoundTripTest(unittest.TestCase):
    def test_every_format_returns_the_same_business_totals(self):
        table = expand(load_base(ROOT / "data" / "orders.csv"), 4000)
        expected = aggregate(table)
        total_quantity = sum(v["quantity"] for v in expected.values())
        with tempfile.TemporaryDirectory() as tmp:
            for v in VARIANTS:
                with self.subTest(variant=label(v)):
                    path = Path(tmp) / f"{label(v)}.{v.ext}"
                    v.write(table, path)
                    data = v.read(path)
                    self.assertEqual(row_count(data), 4000)
                    self.assertEqual(aggregate(data), expected)
                    self.assertEqual(projected_sum(v.project(path)), total_quantity)

    def test_compression_codecs_shrink_files(self):
        table = expand(load_base(ROOT / "data" / "orders.csv"), 20000)
        with tempfile.TemporaryDirectory() as tmp:
            sizes = {}
            for v in VARIANTS:
                path = Path(tmp) / f"{label(v)}.{v.ext}"
                v.write(table, path)
                sizes[label(v)] = path.stat().st_size
        for fmt, raw in (("parquet", "none"), ("orc", "uncompressed"), ("avro", "null")):
            for codec in ("snappy", "zstd" if fmt != "avro" else "zstandard"):
                self.assertLess(sizes[f"{fmt}-{codec}"], sizes[f"{fmt}-{raw}"])
        self.assertLess(sizes["parquet-zstd"], sizes["csv-none"])


class ResultsTest(unittest.TestCase):
    def test_results_report_every_variant_and_all_checks_pass(self):
        path = ROOT / "results" / "results.json"
        self.assertTrue(path.exists(), "results.json missing, run scripts/start-all.sh first")
        report = json.loads(path.read_text())
        self.assertEqual([r["name"] for r in report["results"]], [label(v) for v in VARIANTS])
        self.assertTrue(report["source_matches_csv"])
        for r in report["results"]:
            with self.subTest(variant=r["name"]):
                self.assertTrue(r["aggregation_matches_csv"])
                self.assertEqual(r["rows_read"], report["rows"])
                self.assertEqual(len(r["write_ms"]["runs"]), report["iterations"])


if __name__ == "__main__":
    unittest.main()
