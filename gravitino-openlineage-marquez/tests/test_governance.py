import csv
import json
import os
import unittest
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

GRAVITINO_URL = os.environ.get("GRAVITINO_URL", "http://localhost:27100")
MARQUEZ_URL = os.environ.get("MARQUEZ_URL", "http://localhost:27101")
UI_URL = os.environ.get("UI_URL", "http://localhost:27104")
METALAKE, CATALOG, JOBS = "shop_lake", "shop_pg", "shop_pipeline"
RAW, CLEAN, REVENUE = (f"{CATALOG}.raw.raw_orders", f"{CATALOG}.clean.clean_orders", f"{CATALOG}.gold.revenue_by_category")
TIERS = {"bronze", "silver", "gold"}
ROWS = list(csv.DictReader((Path(__file__).resolve().parent.parent / "data" / "orders.csv").open(newline="")))


def get(url, accept="application/json"):
    with urlopen(Request(url, headers={"Accept": accept}), timeout=30) as r:
        return json.load(r)


def gravitino(path):
    return get(f"{GRAVITINO_URL}/api/metalakes/{METALAKE}{path}", "application/vnd.gravitino.v1+json")


def marquez(path):
    return get(f"{MARQUEZ_URL}/api/v1{path}")


def table(full):
    _, schema, name = full.split(".")
    return gravitino(f"/catalogs/{CATALOG}/schemas/{schema}/tables/{name}")["table"]


def direct_tags(kind, full):
    return {t["name"] for t in gravitino(f"/objects/{kind}/{quote(full)}/tags?details=true")["tags"] if not t.get("inherited")}


def owner(kind, full):
    return gravitino(f"/owners/{kind}/{quote(full)}").get("owner")


def written_datasets():
    return {(o["namespace"], o["name"]) for j in marquez(f"/namespaces/{JOBS}/jobs")["jobs"] for o in j["outputs"]}


def lineage_edges():
    graph = marquez("/lineage?" + urlencode({"nodeId": f"dataset:{METALAKE}:{REVENUE}", "depth": 20}))["graph"]
    return {(i["origin"], o["destination"]) for n in graph if n["type"] == "JOB" for i in n["inEdges"] for o in n["outEdges"]}


def latest_run(job):
    return marquez(f"/namespaces/{JOBS}/jobs/{job}/runs?limit=1")["runs"][0]


def rows_written(run):
    return run["outputDatasetVersions"][0]["facets"]["outputStatistics"]["rowCount"]


class GovernanceTest(unittest.TestCase):
    def test_every_dataset_the_pipeline_writes_is_registered_in_gravitino_with_owner_and_tier(self):
        written = written_datasets()
        self.assertEqual(written, {(METALAKE, RAW), (METALAKE, CLEAN), (METALAKE, REVENUE)})
        for _, full in written:
            with self.subTest(dataset=full):
                self.assertEqual(table(full)["name"], full.split(".")[-1], "a written dataset missing from the catalog is ungoverned")
                self.assertEqual(owner("table", full)["type"], "group", "every table needs an accountable owning team")
                self.assertEqual(len(direct_tags("table", full) & TIERS), 1, "every table sits in exactly one medallion tier")

    def test_owners_follow_the_team_responsible_for_each_layer(self):
        expected = {RAW: "data_engineering", CLEAN: "data_engineering", REVENUE: "analytics"}
        self.assertEqual({t: owner("table", t)["name"] for t in expected}, expected)
        self.assertEqual({s: owner("schema", f"{CATALOG}.{s}")["name"] for s in ("raw", "clean", "gold")},
                         {"raw": "data_engineering", "clean": "data_engineering", "gold": "analytics"})

    def test_pii_is_tagged_at_the_source_and_does_not_reach_clean_or_gold(self):
        self.assertIn("pii", direct_tags("table", RAW))
        self.assertEqual(direct_tags("column", f"{RAW}.customer"), {"pii"}, "the customer column is the personal data")
        for full in (CLEAN, REVENUE):
            with self.subTest(dataset=full):
                columns = [c["name"] for c in table(full)["columns"]]
                self.assertNotIn("customer", columns, "the clean layer must only carry the hash")
                self.assertNotIn("pii", direct_tags("table", full))
        self.assertIn("customer_hash", [c["name"] for c in table(CLEAN)["columns"]])

    def test_every_table_and_column_has_a_comment(self):
        for full in (RAW, CLEAN, REVENUE):
            t = table(full)
            with self.subTest(dataset=full):
                self.assertTrue(t.get("comment"))
                self.assertTrue(all(c.get("comment") for c in t["columns"]), "undocumented columns cannot be governed")


class LineageTest(unittest.TestCase):
    def test_marquez_lineage_has_exactly_the_raw_clean_revenue_edges(self):
        ids = {name: f"dataset:{METALAKE}:{name}" for name in (RAW, CLEAN, REVENUE)}
        edges = lineage_edges()
        self.assertEqual({e for e in edges if e[0].startswith(f"dataset:{METALAKE}:")}, {(ids[RAW], ids[CLEAN]), (ids[CLEAN], ids[REVENUE])})
        self.assertEqual({e for e in edges if e[0].startswith("dataset:file:")}, {("dataset:file:data/orders.csv", ids[RAW])})

    def test_marquez_namespace_holds_only_datasets_registered_in_gravitino(self):
        in_marquez = {d["name"] for d in marquez(f"/namespaces/{METALAKE}/datasets?limit=100")["datasets"]}
        in_gravitino = {f"{CATALOG}.{s}.{t['name']}" for s in ("raw", "clean", "gold")
                        for t in gravitino(f"/catalogs/{CATALOG}/schemas/{s}/tables")["identifiers"]}
        self.assertEqual(in_marquez, in_gravitino)

    def test_marquez_schema_facet_is_the_gravitino_table_schema(self):
        for full in (RAW, CLEAN, REVENUE):
            with self.subTest(dataset=full):
                facet = marquez(f"/namespaces/{METALAKE}/datasets/{quote(full)}")["facets"]["schema"]["fields"]
                self.assertEqual([(f["name"], f["type"]) for f in facet], [(c["name"], c["type"]) for c in table(full)["columns"]])

    def test_latest_runs_completed_and_row_counts_match_the_csv(self):
        categories = {r["category"] for r in ROWS}
        expected = {"load_raw_orders": len(ROWS), "build_clean_orders": len(ROWS), "build_revenue_by_category": len(categories)}
        for job, rows in expected.items():
            run = latest_run(job)
            with self.subTest(job=job):
                self.assertEqual(run["state"], "COMPLETED")
                self.assertIsNotNone(run["startedAt"], "a START event must precede COMPLETE")
                self.assertEqual(rows_written(run), rows)

    def test_runs_of_one_pipeline_execution_happen_in_lineage_order(self):
        started = [latest_run(j)["startedAt"] for j in ("load_raw_orders", "build_clean_orders", "build_revenue_by_category")]
        self.assertEqual(started, sorted(started), "a downstream job must not run before its input was rebuilt")


class RevenueTest(unittest.TestCase):
    def expected(self):
        out = {}
        for r in ROWS:
            c = out.setdefault(r["category"], {"orders": 0, "quantity": 0, "revenue": Decimal(0)})
            c["orders"] += 1
            c["quantity"] += int(r["quantity"])
            c["revenue"] += int(r["quantity"]) * Decimal(r["price"])
        return out

    def test_revenue_per_category_matches_the_csv(self):
        actual = {r["category"]: {"orders": r["orders"], "quantity": r["quantity"], "revenue": Decimal(str(r["revenue"]))}
                  for r in get(f"{UI_URL}/api/revenue")}
        self.assertEqual(actual, self.expected())

    def test_total_revenue_matches_the_csv(self):
        total = sum(Decimal(str(r["revenue"])) for r in get(f"{UI_URL}/api/revenue"))
        self.assertEqual(total, sum(c["revenue"] for c in self.expected().values()))


if __name__ == "__main__":
    unittest.main()
