import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

import vector
from bench import expected_filter, sorted_projection, take_indices
from dataset import DIM, checksums, expand, load_base, normalize
from formats import FORMATS, size_of

ROWS = 20000


def table_of(rows):
    return normalize(expand(load_base(ROOT / "data" / "orders.csv"), rows))


class DatasetTest(unittest.TestCase):
    def test_expansion_is_deterministic_so_runs_are_comparable(self):
        self.assertTrue(table_of(3000).equals(table_of(3000)))

    def test_embeddings_cluster_by_product_so_vector_search_has_meaning(self):
        table = table_of(ROWS)
        vectors = table.column("embedding").combine_chunks().values.to_numpy().reshape(-1, DIM)
        products = table.column("product").to_pylist()
        for row in (0, 777, 12345):
            neighbours = vector.exact(vectors, vectors[row], 10)
            self.assertEqual({products[n] for n in neighbours}, {products[row]})

    def test_checksums_catch_a_single_changed_value(self):
        table = table_of(3000)
        price = table.column("price").to_pylist()
        price[1500] += 0.01
        changed = table.set_column(table.schema.get_field_index("price"), "price", pa.array(price))
        self.assertNotEqual(checksums(changed)["revenue"], checksums(table)["revenue"])

    def test_take_indices_are_sorted_unique_and_repeatable(self):
        indices = take_indices(ROWS, 100)
        self.assertEqual(indices, sorted(set(indices)))
        self.assertEqual(len(indices), 100)
        self.assertEqual(indices, take_indices(ROWS, 100))


class RoundTripTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = table_of(ROWS)
        cls.tmp = tempfile.TemporaryDirectory()
        cls.indices = take_indices(ROWS, 50)
        for fmt in FORMATS:
            fmt.write(cls.table, Path(cls.tmp.name) / f"orders.{fmt.ext}")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def path(self, fmt):
        return Path(self.tmp.name) / f"orders.{fmt.ext}"

    def test_every_format_reads_back_exactly_the_written_table(self):
        for fmt in FORMATS:
            with self.subTest(format=fmt.name):
                scanned = normalize(fmt.scan(self.path(fmt)))
                self.assertTrue(scanned.equals(self.table), "a faster format that changes data is useless")
                self.assertEqual(checksums(scanned), checksums(self.table))

    def test_filter_pushdown_returns_exactly_the_matching_rows(self):
        expected = sorted_projection(expected_filter(self.table))
        self.assertGreater(expected.num_rows, 0)
        for fmt in FORMATS:
            with self.subTest(format=fmt.name):
                result = fmt.filter(self.path(fmt))
                self.assertEqual(result.column_names, ["order_id", "price"], "projection must drop other columns")
                self.assertTrue(sorted_projection(result).equals(expected))

    def test_take_returns_the_requested_rows_in_order(self):
        expected = normalize(self.table.take(pa.array(self.indices)))
        for fmt in FORMATS:
            with self.subTest(format=fmt.name):
                taken = normalize(fmt.take(self.path(fmt), self.indices))
                self.assertEqual(taken.column("order_id").to_pylist(), [i + 1 for i in self.indices])
                self.assertTrue(taken.equals(expected))

    def test_columnar_encodings_beat_the_raw_arrow_size_on_scalar_columns(self):
        scalar = self.table.drop_columns(["embedding"])
        with tempfile.TemporaryDirectory() as tmp:
            for fmt in FORMATS:
                with self.subTest(format=fmt.name):
                    path = Path(tmp) / f"scalar.{fmt.ext}"
                    fmt.write(scalar, path)
                    self.assertLess(size_of(path), scalar.nbytes)


class LanceVectorTest(unittest.TestCase):
    def test_ivf_pq_index_finds_the_exact_neighbours(self):
        table = table_of(ROWS)
        vectors = table.column("embedding").combine_chunks().values.to_numpy().reshape(-1, DIM)
        lance_fmt = next(f for f in FORMATS if f.name == "lance")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orders.lance"
            lance_fmt.write(table, path)
            vector.build_index(path)
            recalls = []
            for row in np.random.default_rng(3).choice(ROWS, 10, replace=False):
                found = vector.nearest(path, vectors[row], 10)
                self.assertEqual(found.column("order_id")[0].as_py(), int(row) + 1, "a stored vector is its own nearest neighbour")
                self.assertTrue(pc.all(pc.equal(found.column("category"), table.column("category")[int(row)])).as_py())
                recalls.append(vector.recall(found.column("order_id").to_pylist(), vector.exact(vectors, vectors[row], 10)))
            self.assertGreaterEqual(sum(recalls) / len(recalls), 0.9)


class ResultsTest(unittest.TestCase):
    def test_results_cover_every_format_and_every_check_passed(self):
        path = ROOT / "results" / "results.json"
        self.assertTrue(path.exists(), "results.json missing, run scripts/bench.sh first")
        report = json.loads(path.read_text())
        self.assertTrue(report["all_ok"])
        self.assertEqual([f["name"] for f in report["formats"]], [f.name for f in FORMATS])
        for f in report["formats"]:
            with self.subTest(format=f["name"]):
                self.assertTrue(f["ok"])
                self.assertEqual(f["checks"]["checksums"], report["source_checksums"])
                self.assertEqual(f["checks"]["filter_rows"], report["filter"]["expected_rows"])
                self.assertEqual(f["checks"]["take_rows"], report["take_n"])
                for metric in ("write_ms", "scan_ms", "filter_ms", "take_ms"):
                    self.assertEqual(len(f[metric]["runs"]), report["iterations"])
        self.assertGreaterEqual(report["vector"]["recall_at_k"], 0.9)


if __name__ == "__main__":
    unittest.main()
