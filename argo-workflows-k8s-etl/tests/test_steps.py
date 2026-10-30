import json
import tempfile
import unittest
from pathlib import Path
from tests import expected
import data
import etl


class StepsTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.batch = etl.extract(5, 300, self.dir)

    def test_extract_is_reproducible_from_the_seed(self):
        lines = (self.dir / "orders.json").read_text().splitlines()
        self.assertEqual([json.loads(line) for line in lines], data.orders(5, 300))
        self.assertEqual(json.loads((self.dir / "regions.json").read_text()), sorted({o["region"] for o in self.batch}))
        self.assertEqual((self.dir / "count").read_text(), "300")

    def test_transform_fails_only_the_first_attempt_of_the_flaky_region(self):
        source = self.dir / "orders.json"
        with self.assertRaises(SystemExit) as failed:
            etl.transform("br", source, self.dir / "br.json", 75000, "br", 0)
        self.assertNotEqual(failed.exception.code, 0)
        self.assertFalse((self.dir / "br.json").exists())
        etl.transform("br", source, self.dir / "br.json", 75000, "br", 1)
        etl.transform("us", source, self.dir / "us.json", 75000, "br", 0)
        self.assertTrue((self.dir / "br.json").exists())
        self.assertTrue((self.dir / "us.json").exists())

    def test_transform_and_merge_match_independent_totals(self):
        want = expected.region_totals(5, 300, 75000)
        parts = self.dir / "parts"
        for region in json.loads((self.dir / "regions.json").read_text()):
            etl.transform(region, self.dir / "orders.json", parts / f"{region}.json", 75000, "", 0)
        report = etl.merge(parts, self.dir / "out")
        got = {r["region"]: {k: v for k, v in r.items() if k != "region"} for r in report["regions"]}
        self.assertEqual(got, want)
        self.assertEqual(report["orders"], 300)
        self.assertEqual(report["cents"], sum(o["cents"] for o in data.orders(5, 300)))
        self.assertEqual(report["max_region_cents"], max(t["cents"] for t in want.values()))
        self.assertEqual((self.dir / "out" / "max_region_cents").read_text(), str(report["max_region_cents"]))


if __name__ == "__main__":
    unittest.main()
