import json
import os
import unittest
import urllib.error
import urllib.request

import numpy as np

API = os.environ.get("API_URL", "http://localhost:8080")
DATA = os.environ.get("DATA_DIR", "/data")
PARTITIONS = 8


def get(path):
    with urllib.request.urlopen(API + path, timeout=60) as r:
        return json.loads(r.read())


def raw(parts):
    cols = {"user": [], "platform": [], "latency": [], "item": []}
    for p in parts:
        with np.load(os.path.join(DATA, f"part-{p}.npz")) as z:
            for k in cols:
                cols[k].append(z[k])
    return {k: np.concatenate(v) for k, v in cols.items()}


def distinct(values):
    return int(np.unique(values).size)


def true_rank_interval(values, v):
    return float(np.sum(values < v)) / values.size, float(np.sum(values <= v)) / values.size


def three_sigma_hll_error(results):
    lg_k = results["config"]["hll_lg_k"]
    two_sigma = next(r["bound"] for r in results["hll_sweep"] if r["lg_k"] == lg_k)
    return two_sigma * 3 / 2


class SketchesAgainstRawData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = get("/api/results")
        cls.rows = raw(range(PARTITIONS))
        cls.merged = cls.results["merged"]

    def test_row_count_is_the_whole_generated_dataset(self):
        self.assertEqual(self.rows["user"].size, 10_000_000)
        self.assertEqual(self.merged["kll"]["n"], self.rows["latency"].size)
        self.assertEqual(self.merged["frequent"]["total"], self.rows["item"].size)

    def test_hll_distinct_users_is_inside_its_error_bounds(self):
        truth = distinct(self.rows["user"])
        hll = self.merged["hll"]
        self.assertLessEqual(hll["lower"], truth)
        self.assertGreaterEqual(hll["upper"], truth)
        self.assertLess(abs(hll["estimate"] - truth) / truth, three_sigma_hll_error(self.results))

    def test_hll_error_stays_inside_the_configured_bound_for_every_lg_k(self):
        truth = distinct(self.rows["user"])
        sweep = self.results["hll_sweep"]
        for row in sweep:
            err = abs(row["estimate"] - truth) / truth
            self.assertLessEqual(err, row["bound"] * 3 / 2, f"lg_k={row['lg_k']} three sigma")
            self.assertLessEqual(row["lower"], truth)
            self.assertGreaterEqual(row["upper"], truth)
        self.assertLess(sweep[-1]["bound"], sweep[0]["bound"] / 10)
        self.assertGreater(sweep[-1]["bytes"], sweep[0]["bytes"] * 100)

    def test_kll_quantiles_are_within_the_rank_error_guarantee(self):
        lat = self.rows["latency"]
        eps = self.merged["kll"]["rank_error"]
        for q, v in self.merged["kll"]["quantiles"].items():
            lo, hi = true_rank_interval(lat, np.float32(v))
            miss = 0.0 if lo <= float(q) <= hi else min(abs(float(q) - lo), abs(float(q) - hi))
            self.assertLessEqual(miss, eps, f"q={q} true rank [{lo},{hi}]")

    def test_kll_rank_error_bound_holds_for_every_k(self):
        for row in self.results["kll_sweep"]:
            self.assertLessEqual(row["worst_rank_error"], row["bound"], f"k={row['k']}")
        bounds = [r["bound"] for r in self.results["kll_sweep"]]
        self.assertEqual(bounds, sorted(bounds, reverse=True))

    def test_theta_set_operations_contain_the_exact_answer(self):
        web = np.unique(self.rows["user"][self.rows["platform"] == 0])
        mobile = np.unique(self.rows["user"][self.rows["platform"] == 1])
        in_mobile = np.isin(web, mobile)
        truth = {
            "web": web.size,
            "mobile": mobile.size,
            "union": web.size + mobile.size - int(in_mobile.sum()),
            "intersection": int(in_mobile.sum()),
            "web_not_mobile": int((~in_mobile).sum()),
        }
        theta = self.merged["theta"]
        for op, count in truth.items():
            self.assertLessEqual(theta[op]["lower"], count, op)
            self.assertGreaterEqual(theta[op]["upper"], count, op)
        self.assertGreater(truth["intersection"], 0)
        self.assertGreater(truth["web_not_mobile"], 0)

    def test_frequent_items_has_no_false_negatives(self):
        counts = np.bincount(self.rows["item"])
        freq = self.merged["frequent"]
        heavy = set(np.nonzero(counts > freq["max_error"])[0].tolist())
        self.assertTrue(heavy)
        self.assertTrue(heavy.issubset(set(freq["all_items"])))
        for row in freq["items"]:
            true = int(counts[row["item"]])
            self.assertLessEqual(row["lower"], true)
            self.assertGreaterEqual(row["upper"], true)
        top_true = set(np.argsort(-counts)[: len(freq["items"])].tolist())
        self.assertEqual(top_true, {r["item"] for r in freq["items"]})

    def test_count_min_never_underestimates_and_stays_within_eps_n(self):
        counts = np.bincount(self.rows["item"])
        freq = self.merged["frequent"]
        slack = freq["cm_relative_error"] * freq["total"]
        for row in freq["items"]:
            true = int(counts[row["item"]])
            self.assertGreaterEqual(row["cm_estimate"], true)
            self.assertLessEqual(row["cm_estimate"] - true, slack)

    def test_sketches_are_orders_of_magnitude_smaller_than_exact_state(self):
        exact_users = np.unique(self.rows["user"]).nbytes
        exact_lat = self.rows["latency"].nbytes
        self.assertLess(self.merged["hll"]["bytes"] * 500, exact_users)
        self.assertLess(self.merged["kll"]["bytes"] * 500, exact_lat)
        self.assertLess(self.merged["theta"]["web"]["bytes"] * 50, exact_users)
        exact_items = np.count_nonzero(np.bincount(self.rows["item"])) * 12
        self.assertLess(self.merged["frequent"]["bytes"] + self.merged["frequent"]["cm_bytes"], exact_items / 5)

    def test_each_partition_sketch_estimates_its_own_partition(self):
        for part in self.results["partitions"]:
            truth = distinct(raw([part["partition"]])["user"])
            self.assertEqual(part["exact_distinct"], truth)
            self.assertLessEqual(part["hll_lower"], truth)
            self.assertGreaterEqual(part["hll_upper"], truth)

    def test_merging_stored_partition_sketches_answers_any_subset(self):
        parts = [1, 4, 6]
        merged = get("/api/merge?partitions=" + ",".join(map(str, parts)))
        rows = raw(parts)
        truth = distinct(rows["user"])
        self.assertEqual(merged["partitions"], parts)
        self.assertLessEqual(merged["hll"]["lower"], truth)
        self.assertGreaterEqual(merged["hll"]["upper"], truth)
        self.assertEqual(merged["kll"]["n"], rows["latency"].size)
        eps = merged["kll"]["rank_error"]
        for q, v in merged["kll"]["quantiles"].items():
            lo, hi = true_rank_interval(rows["latency"], np.float32(v))
            self.assertTrue(lo - eps <= float(q) <= hi + eps, q)
        overlap = int(np.isin(np.unique(rows["user"][rows["platform"] == 0]), rows["user"][rows["platform"] == 1]).sum())
        self.assertLessEqual(merged["theta"]["intersection"]["lower"], overlap)
        self.assertGreaterEqual(merged["theta"]["intersection"]["upper"], overlap)

    def test_merged_distinct_is_less_than_sum_of_partitions(self):
        summed = sum(p["hll_estimate"] for p in self.results["partitions"])
        truth = distinct(self.rows["user"])
        self.assertGreater(summed, truth * 2)
        self.assertLessEqual(self.merged["hll"]["lower"], truth)
        self.assertGreaterEqual(self.merged["hll"]["upper"], truth)

    def test_merged_hll_agrees_with_a_single_pass_sketch(self):
        truth = distinct(self.rows["user"])
        single = self.results["single_pass_hll"]
        self.assertLessEqual(single["lower"], truth)
        self.assertGreaterEqual(single["upper"], truth)
        self.assertLess(abs(single["estimate"] - self.merged["hll"]["estimate"]) / truth, three_sigma_hll_error(self.results))

    def test_exact_endpoint_matches_raw_data(self):
        exact = get("/api/exact?partitions=2")
        rows = raw([2])
        self.assertEqual(exact["distinct_users"], distinct(rows["user"]))
        self.assertEqual(exact["rows"], rows["user"].size)

    def test_bad_partition_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            get("/api/merge?partitions=9")
        self.assertEqual(ctx.exception.code, 400)

    def test_ui_page_has_every_tab(self):
        with urllib.request.urlopen(API + "/", timeout=10) as r:
            html = r.read().decode()
        for tab in ["HLL", "KLL", "Theta", "Heavy hitters", "Merge"]:
            self.assertIn(tab, html)


if __name__ == "__main__":
    unittest.main()
