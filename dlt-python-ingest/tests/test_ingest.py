import base64
import csv
import json
import os
import unittest
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime
from pathlib import Path

UI_URL = os.environ.get("UI_URL", "http://localhost:26901")
CSV_FILE = Path(__file__).resolve().parent.parent / "data" / "orders.csv"


def call(path, method="GET"):
    request = urllib.request.Request(UI_URL + path, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as res:
            return json.load(res)
    except urllib.error.HTTPError as e:
        raise AssertionError(f"{method} {path} failed: {e.read().decode()}")


def sql(statement):
    return call("/api/sql?q=" + urllib.parse.quote(statement))["rows"]


def scalar(statement):
    return sql(statement)[0][0]


def columns(table):
    return {r[0] for r in sql(f"SELECT column_name FROM information_schema.columns WHERE table_schema = 'ingest' AND table_name = '{table}'")}


def all_customers():
    page, pages, rows = 1, 1, []
    while page <= pages:
        body = call(f"/source/customers?page={page}&page_size=5")
        rows += body["data"]
        pages = body["pages"]
        page += 1
    return rows


class IngestScenario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if hasattr(IngestScenario, "final"):
            return
        s = IngestScenario
        with CSV_FILE.open() as f:
            s.csv_rows = list(csv.DictReader(f))
        call("/api/reset", "POST")
        s.first = call("/api/run", "POST")
        s.first_orders = scalar("SELECT count(*) FROM ingest.orders")
        s.first_columns = columns("orders")
        s.rerun = call("/api/run", "POST")
        s.rerun_orders = scalar("SELECT count(*) FROM ingest.orders")
        s.changes = call("/api/changes", "POST")
        s.after_changes = call("/api/run", "POST")
        s.final = call("/api/run", "POST")
        s.schema = call("/api/schema")


class FirstLoad(IngestScenario):
    def test_first_run_loads_every_csv_order_exactly_once(self):
        self.assertEqual(self.first_orders, len(self.csv_rows))
        self.assertEqual(self.first["row_counts"]["orders"], len(self.csv_rows))
        self.assertEqual(scalar("SELECT count(DISTINCT order_id) FROM ingest.orders"), scalar("SELECT count(*) FROM ingest.orders"))

    def test_loaded_values_match_the_csv(self):
        expected = {int(r["order_id"]): (r["customer"], int(r["quantity"]), float(r["price"])) for r in self.csv_rows}
        untouched = set(expected) - {u["order_id"] for u in self.changes["updated"]} - set(self.changes["deleted"])
        rows = {r[0]: (r[1], r[2], float(r[3])) for r in sql("SELECT order_id, customer, quantity, price FROM ingest.orders")}
        for order_id in untouched:
            self.assertEqual(rows[order_id], expected[order_id], order_id)

    def test_rest_source_is_paginated_and_every_page_is_loaded(self):
        page = call("/source/customers?page=1&page_size=5")
        self.assertEqual(len(page["data"]), 5)
        self.assertGreater(page["pages"], 1)
        distinct_customers = len({r["customer"] for r in self.csv_rows})
        self.assertEqual(self.first["row_counts"]["customers"], distinct_customers)
        self.assertEqual(scalar("SELECT count(*) FROM ingest.customers"), distinct_customers)


class Incremental(IngestScenario):
    def test_rerun_without_source_changes_loads_nothing_and_duplicates_nothing(self):
        self.assertEqual(self.rerun["row_counts"].get("orders", 0), 0)
        self.assertEqual(self.rerun["row_counts"].get("customers", 0), 0)
        self.assertEqual(self.rerun_orders, self.first_orders)
        self.assertEqual(self.final["row_counts"], {})

    def test_run_after_changes_only_loads_the_changed_rows(self):
        c = self.changes
        self.assertEqual(self.after_changes["row_counts"]["orders"], len(c["updated"]) + len(c["deleted"]) + len(c["inserted"]))
        self.assertEqual(self.after_changes["row_counts"]["customers"], len(c["customers"]))
        self.assertLess(self.after_changes["row_counts"]["orders"], self.first_orders)


class Merge(IngestScenario):
    def test_updated_source_rows_replace_the_destination_row(self):
        for u in self.changes["updated"]:
            rows = sql(f"SELECT quantity, coupon FROM ingest.orders WHERE order_id = {u['order_id']}")
            self.assertEqual(rows, [[u["quantity"], "SAVE10"]])

    def test_soft_deleted_source_rows_are_removed_from_the_destination(self):
        for order_id in self.changes["deleted"]:
            self.assertEqual(scalar(f"SELECT count(*) FROM ingest.orders WHERE order_id = {order_id}"), 0)
        self.assertEqual(scalar("SELECT count(*) FROM ingest.orders WHERE deleted"), 0)

    def test_destination_mirrors_live_source_rows_without_duplicates(self):
        expected = len(self.csv_rows) - len(self.changes["deleted"]) + len(self.changes["inserted"])
        self.assertEqual(self.changes["counts"]["orders_live"], expected)
        self.assertEqual(scalar("SELECT count(*) FROM ingest.orders"), expected)
        self.assertEqual(scalar("SELECT count(DISTINCT order_id) FROM ingest.orders"), expected)
        for i in self.changes["inserted"]:
            self.assertEqual(sql(f"SELECT customer, coupon FROM ingest.orders WHERE order_id = {i['order_id']}"), [[i["customer"], "WELCOME"]])


class SchemaEvolution(IngestScenario):
    def test_new_source_column_is_added_to_the_destination_table(self):
        self.assertNotIn("coupon", self.first_columns)
        self.assertIn("coupon", columns("orders"))
        self.assertIn("orders.coupon", self.after_changes["new_columns"])
        untouched = scalar("SELECT count(*) FROM ingest.orders WHERE coupon IS NULL")
        self.assertEqual(untouched, len(self.csv_rows) - len(self.changes["deleted"]) - len(self.changes["updated"]))

    def test_new_nested_json_object_is_flattened_into_new_columns(self):
        self.assertTrue({"loyalty__points", "loyalty__level"} <= columns("customers"))
        for c in self.changes["customers"]:
            rows = sql(f"SELECT tier, loyalty__points, loyalty__level FROM ingest.customers WHERE id = {c['id']}")
            self.assertEqual(rows, [["platinum", c["loyalty"]["points"], "platinum"]])

    def test_evolution_is_recorded_as_a_new_schema_version(self):
        versions = self.schema["versions"]
        self.assertGreaterEqual(len(versions), 2)
        self.assertNotIn("orders.coupon", versions[0]["added_columns"])
        self.assertIn("orders.coupon", versions[-1]["added_columns"])
        self.assertIn("customers.loyalty__points", versions[-1]["added_columns"])
        self.assertNotEqual(self.first["schema_hash"], self.after_changes["schema_hash"])
        self.assertEqual(self.after_changes["schema_hash"], self.final["schema_hash"])


class NestedTables(IngestScenario):
    def test_nested_lists_become_child_tables_linked_to_their_parent(self):
        source = all_customers()
        self.assertEqual(scalar("SELECT count(*) FROM ingest.customers__addresses"), sum(len(c["addresses"]) for c in source))
        self.assertEqual(scalar("SELECT count(*) FROM ingest.customers__tags"), sum(len(c["tags"]) for c in source))
        orphans = scalar("SELECT count(*) FROM ingest.customers__addresses a LEFT JOIN ingest.customers c ON a._dlt_parent_id = c._dlt_id WHERE c._dlt_id IS NULL")
        self.assertEqual(orphans, 0)

    def test_merge_replaces_the_child_rows_of_an_updated_parent(self):
        for c in self.changes["customers"]:
            rows = sql(
                f"SELECT a.kind FROM ingest.customers__addresses a JOIN ingest.customers c ON a._dlt_parent_id = c._dlt_id "
                f"WHERE c.id = {c['id']} ORDER BY a._dlt_list_idx"
            )
            self.assertEqual(len(rows), c["addresses"])
            self.assertEqual(rows[-1], ["shipping"])


class LoadState(IngestScenario):
    def test_every_run_commits_one_completed_load_package(self):
        runs = [self.first, self.rerun, self.after_changes, self.final]
        load_ids = [i for r in runs for i in r["load_ids"]]
        rows = sql("SELECT load_id, status FROM ingest._dlt_loads ORDER BY load_id")
        self.assertEqual(sorted(load_ids), [r[0] for r in rows])
        self.assertEqual({r[1] for r in rows}, {0})
        self.assertFalse(any(r["failed_jobs"] for r in runs))

    def test_every_loaded_row_points_to_a_committed_load(self):
        dangling = scalar("SELECT count(*) FROM ingest.orders o LEFT JOIN ingest._dlt_loads l ON o._dlt_load_id = l.load_id WHERE l.load_id IS NULL")
        self.assertEqual(dangling, 0)
        changed = {u["order_id"] for u in self.changes["updated"]} | {i["order_id"] for i in self.changes["inserted"]}
        reloaded = {r[0] for r in sql(f"SELECT order_id FROM ingest.orders WHERE _dlt_load_id = '{self.after_changes['load_ids'][0]}'")}
        self.assertEqual(reloaded, changed)

    def test_incremental_cursor_is_stored_in_the_destination_state(self):
        blob = scalar("SELECT state FROM ingest._dlt_pipeline_state ORDER BY version DESC LIMIT 1")
        resources = json.loads(zlib.decompress(base64.b64decode(blob)))["sources"]["shop"]["resources"]
        cursor = resources["orders"]["incremental"]["updated_at"]
        last_value = datetime.fromisoformat(cursor["last_value"].lstrip(""))
        latest = datetime.fromisoformat(scalar("SELECT max(updated_at) FROM ingest.orders"))
        self.assertEqual(last_value, latest)
        c = self.changes
        self.assertEqual(len(cursor["unique_hashes"]), len(c["updated"]) + len(c["deleted"]) + len(c["inserted"]))
        self.assertIn("last_value", resources["customers"]["incremental"]["updated_at"])


if __name__ == "__main__":
    unittest.main()
