import json
import os
import unittest
import urllib.error
import urllib.parse
import urllib.request

UI_URL = os.environ.get("UI_URL", "http://localhost:26800")


def get(path, **params):
    with urllib.request.urlopen(f"{UI_URL}{path}?{urllib.parse.urlencode(params)}", timeout=120) as r:
        return json.load(r)


class ResultsApiTest(unittest.TestCase):
    def test_health(self):
        self.assertEqual(get("/api/health"), {"status": "UP"})

    def test_results_show_three_formats_all_verified(self):
        report = get("/api/results")
        self.assertTrue(report["all_ok"])
        self.assertEqual({f["name"] for f in report["formats"]}, {"parquet", "lance", "vortex"})
        self.assertEqual(report["rows"], report["source_checksums"]["rows"])

    def test_every_format_holds_the_same_rows_in_the_ui_lake(self):
        rows = get("/api/results")["rows"]
        order_id_sum = rows * (rows + 1) // 2
        for f in get("/api/results")["formats"]:
            with self.subTest(format=f["name"]):
                self.assertEqual(f["checks"]["checksums"]["order_id_sum"], order_id_sum, "order ids 1..rows, none lost or duplicated")


class LiveTakeTest(unittest.TestCase):
    def test_live_take_returns_identical_rows_from_every_format(self):
        response = get("/api/take", n=250, seed=12)
        self.assertEqual(len(response["results"]), 3)
        for r in response["results"]:
            with self.subTest(format=r["name"]):
                self.assertEqual(r["rows"], 250)
                self.assertTrue(r["same_as_parquet"])
        self.assertEqual(response["indices"], sorted(response["indices"]))

    def test_different_seed_fetches_different_rows(self):
        self.assertNotEqual(get("/api/take", n=20, seed=1)["indices"], get("/api/take", n=20, seed=2)["indices"])


class LiveNearestTest(unittest.TestCase):
    def test_query_row_is_its_own_nearest_neighbour_and_neighbours_share_its_product(self):
        response = get("/api/nearest", order_id=4242, k=10)
        results = response["results"]
        self.assertEqual(len(results), 10)
        self.assertEqual(results[0]["order_id"], 4242)
        self.assertEqual(results[0]["_distance"], 0.0)
        self.assertEqual({r["product"] for r in results}, {response["product"]})
        distances = [r["_distance"] for r in results]
        self.assertEqual(distances, sorted(distances))
        self.assertGreaterEqual(response["recall"], 0.8, "the ANN index must agree with the flat search")

    def test_bad_input_is_a_client_error(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            get("/api/take", n="many")
        self.assertEqual(ctx.exception.code, 400)
        ctx.exception.close()


if __name__ == "__main__":
    unittest.main()
