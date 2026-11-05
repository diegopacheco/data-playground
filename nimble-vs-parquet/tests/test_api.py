import json
import os
import unittest
import urllib.error
import urllib.request

UI_URL = os.environ.get("UI_URL", "http://localhost:31800")
FORMATS = ["nimble", "parquet_snappy", "parquet_zstd"]


def get(path):
    with urllib.request.urlopen(UI_URL + path, timeout=120) as res:
        return res.status, json.loads(res.read())


def status_of(path):
    try:
        return get(path)[0]
    except urllib.error.HTTPError as e:
        e.close()
        return e.code


class ResultsApiTest(unittest.TestCase):
    def test_health(self):
        self.assertEqual(get("/api/health"), (200, {"status": "UP"}))

    def test_results_show_both_tables_in_every_format_all_verified(self):
        _, results = get("/api/results")
        self.assertTrue(results["all_ok"])
        widths = {t["name"]: t["columns"] for t in results["tables"]}
        self.assertGreaterEqual(widths["wide"], 1000)
        self.assertLess(widths["normal"], 20)
        for t in results["tables"]:
            self.assertEqual([f["name"] for f in t["formats"]], FORMATS)


class LiveReadsTest(unittest.TestCase):
    def test_live_projection_matches_the_source_in_every_format(self):
        _, body = get("/api/project?table=wide&count=7")
        self.assertEqual(len(body["columns"]), 7)
        self.assertEqual(len(set(body["columns"])), 7)
        self.assertEqual([r["name"] for r in body["results"]], FORMATS)
        rows = {r["rows"] for r in body["results"]}
        self.assertEqual(len(rows), 1)
        for r in body["results"]:
            self.assertTrue(r["matches_source"], r["name"])
            self.assertGreater(r["ms"], 0)

    def test_live_metadata_reports_the_table_width(self):
        _, results = get("/api/results")
        widths = {t["name"]: t["columns"] for t in results["tables"]}
        for name, width in widths.items():
            _, body = get(f"/api/meta?table={name}")
            for r in body["results"]:
                self.assertEqual(r["columns"], width, (name, r["name"]))
                self.assertGreater(r["footer_bytes"], 0)

    def test_bad_input_is_a_client_error(self):
        self.assertEqual(status_of("/api/project?table=wide&count=0"), 400)
        self.assertEqual(status_of("/api/project?table=wide&count=abc"), 400)
        self.assertEqual(status_of("/api/project?table=nope"), 400)
        self.assertEqual(status_of("/api/meta?table=nope"), 400)


if __name__ == "__main__":
    unittest.main()
