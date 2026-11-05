import json
import os
import shutil
import tempfile
import unittest

import numpy as np
import pyarrow as pa

import bench
import dataset
import rawcols
from checksums import table_checksums
from formats import FORMATS, file_path, run_step

MASK = (1 << 64) - 1
LAKE = os.environ.get("LAKE", "/lake")
RESULTS = os.environ.get("RESULTS", "/bench/results/results.json")


def py_splitmix(x):
    x = (x + 0x9E3779B97F4A7C15) & MASK
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK
    return x ^ (x >> 31)


def py_checksum(values, kind):
    total = 0
    for i, v in enumerate(values):
        if kind == "bigint":
            bits = v & MASK
        elif kind == "double":
            bits = int(np.array([v], dtype="<f8").view("<u8")[0])
        else:
            raw = v.encode()
            bits = py_splitmix(len(raw))
            for j, b in enumerate(raw):
                bits = (bits + py_splitmix((b << 32) | j)) & MASK
        total = (total + py_splitmix((bits + i) & MASK)) & MASK
    return str(total)


class Workspace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.addClassCleanup(shutil.rmtree, cls.tmp)

    def prepare(self, name, table):
        bench.LAKE = self.tmp
        return bench.prepare(name, table)


class ChecksumTest(Workspace):
    def test_vectorized_checksum_equals_a_plain_python_reimplementation(self):
        table = pa.table({"a": [5, -3, 0, 2**62], "b": [1.5, -0.0, 3.25, 1e300], "c": ["", "x", "nimble", "parquet"]})
        sums = table_checksums(table)
        self.assertEqual(sums["a"], py_checksum([5, -3, 0, 2**62], "bigint"))
        self.assertEqual(sums["b"], py_checksum([1.5, -0.0, 3.25, 1e300], "double"))
        self.assertEqual(sums["c"], py_checksum(["", "x", "nimble", "parquet"], "varchar"))

    def test_checksum_catches_a_changed_value_and_a_row_swap(self):
        base = pa.table({"a": [1, 2, 3], "s": ["ab", "cd", "ef"]})
        changed = pa.table({"a": [1, 2, 4], "s": ["ab", "cd", "eg"]})
        swapped = pa.table({"a": [2, 1, 3], "s": ["cd", "ab", "ef"]})
        for other in (changed, swapped):
            self.assertNotEqual(table_checksums(base)["a"], table_checksums(other)["a"])
            self.assertNotEqual(table_checksums(base)["s"], table_checksums(other)["s"])

    def test_nimble_cpp_checksums_agree_with_python_on_the_same_bytes(self):
        table = dataset.normal_table(3000, seed=11)
        table_dir, source = self.prepare("agree", table)
        run_step("nimble", "write", table_dir, 1)
        scan = run_step("nimble", "scan", table_dir, 1)
        self.assertEqual(scan["checksums"], source["checksums"])

    def test_same_bytes_detects_a_single_flipped_byte(self):
        table_dir, _ = self.prepare("flip", dataset.normal_table(500, seed=3))
        copy = os.path.join(self.tmp, "flip_copy")
        shutil.copytree(os.path.join(table_dir, "source"), copy)
        self.assertTrue(rawcols.same_bytes(os.path.join(table_dir, "source"), copy))
        with open(os.path.join(copy, "c6.bin"), "r+b") as f:
            f.seek(100)
            byte = f.read(1)
            f.seek(100)
            f.write(bytes([byte[0] ^ 1]))
        self.assertFalse(rawcols.same_bytes(os.path.join(table_dir, "source"), copy))


class RoundTripTest(Workspace):
    def check_table(self, name, table, project):
        columns = dataset.projection(table, project)
        table_dir, source = self.prepare(name, table)
        for fmt in FORMATS:
            with self.subTest(fmt=fmt):
                result = bench.measure(fmt, table_dir, source, columns, 2)
                self.assertTrue(all(result["checks"].values()), result["checks"])
                self.assertEqual(sorted(result["project_checksums"]), sorted(columns))
                self.assertEqual(result["size_bytes"], os.path.getsize(file_path(table_dir, fmt)))
        return table_dir

    def test_wide_table_round_trips_in_every_format(self):
        self.check_table("wide", dataset.wide_table(300, 400), 5)

    def test_normal_table_round_trips_in_every_format(self):
        self.check_table("normal", dataset.normal_table(20000), 2)

    def test_projection_returns_only_the_requested_columns(self):
        table = dataset.wide_table(200, 300)
        table_dir, source = self.prepare("proj", table)
        wanted = ["f00010", "f00019", "f00123"]
        for fmt in FORMATS:
            run_step(fmt, "write", table_dir, 1)
            out = run_step(fmt, "project", table_dir, 1, wanted)
            self.assertEqual(out["checksums"], {c: source["checksums"][c] for c in wanted})

    def test_a_corrupted_nimble_file_is_rejected(self):
        table_dir, _ = self.prepare("corrupt", dataset.normal_table(2000, seed=5))
        run_step("nimble", "write", table_dir, 1)
        path = file_path(table_dir, "nimble")
        with open(path, "r+b") as f:
            f.truncate(os.path.getsize(path) - 4)
        with self.assertRaises(RuntimeError):
            run_step("nimble", "meta", table_dir, 1)


class ResultsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(RESULTS) as f:
            cls.results = json.load(f)

    def test_results_cover_both_tables_every_format_and_every_check_passed(self):
        self.assertTrue(self.results["all_ok"])
        self.assertEqual(sorted(t["name"] for t in self.results["tables"]), ["normal", "wide"])
        for t in self.results["tables"]:
            self.assertEqual([f["name"] for f in t["formats"]], FORMATS)
            for f in t["formats"]:
                self.assertTrue(all(f["checks"].values()), (t["name"], f["name"]))
                self.assertEqual(len(f["scan_ms"]["runs"]), self.results["iterations"] + 1)

    def test_reported_sizes_are_the_real_files_in_the_lake(self):
        for t in self.results["tables"]:
            for f in t["formats"]:
                self.assertEqual(f["size_bytes"], os.path.getsize(file_path(os.path.join(LAKE, t["name"]), f["name"])))

    def test_wide_projection_is_cheaper_than_a_full_scan_in_every_format(self):
        wide = next(t for t in self.results["tables"] if t["name"] == "wide")
        for f in wide["formats"]:
            self.assertLess(f["project_ms"]["median"] * 5, f["scan_ms"]["median"], f["name"])

    def test_sweep_files_had_the_configured_number_of_columns(self):
        widths = [p["columns"] for p in self.results["sweep"]]
        self.assertEqual(widths, sorted(widths))
        self.assertTrue(all(p["ok"] for p in self.results["sweep"]))
        for t in self.results["tables"]:
            meta = run_step("nimble", "meta", os.path.join(LAKE, t["name"]), 1)
            self.assertEqual(meta["columns"], t["columns"])


if __name__ == "__main__":
    unittest.main()
