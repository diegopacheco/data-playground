import csv
import json
import os
import re
import sys
import time
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import data
import sources

UI = os.environ.get("UI_URL", "http://localhost:8080")
COUNTRIES = {"US", "BR", "DE", "JP"}
DISCOUNT = {"gold": 10, "silver": 5}


def customers_from_csv():
    with open(data.CUSTOMERS_CSV, newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def violation(o):
    if not o.get("id"):
        return "missing id"
    if not isinstance(o.get("customer_id"), str) or not re.fullmatch(r"c\d{3}", o["customer_id"]):
        return "invalid customer_id"
    if not is_int(o.get("qty")) or not 1 <= o["qty"] <= 100:
        return "qty must be an integer between 1 and 100"
    if not is_int(o.get("unit_price_cents")) or o["unit_price_cents"] < 1:
        return "unit_price_cents must be a positive integer"
    if "@" not in str(o.get("email", "")):
        return "invalid email"
    if str(o.get("country", "")).upper() not in COUNTRIES:
        return "unsupported country"
    return None


def priced(o, customer):
    total = o["qty"] * o["unit_price_cents"]
    discount = total * DISCOUNT.get(customer["tier"], 0) // 100
    net = total - discount
    return {
        "id": o["id"], "run_id": o["run_id"], "customer_id": o["customer_id"], "sku": o.get("sku", "UNKNOWN"),
        "qty": o["qty"], "unit_price_cents": o["unit_price_cents"], "email": o["email"].strip().lower(),
        "country": o["country"].upper(), "channel": o.get("channel", "web"),
        "customer_name": customer["name"], "tier": customer["tier"],
        "total_cents": total, "discount_cents": discount, "net_cents": net,
        "priority": "high" if net >= 50000 else "normal",
    }


def expected(rows):
    people = customers_from_csv()
    out = {"clean": {}, "dlq": [], "loadtest": 0, "duplicates": 0, "invalid": 0}
    seen = set()
    for o in rows:
        reason = violation(o)
        if reason:
            out["invalid"] += 1
            out["dlq"].append((o.get("id"), reason))
            continue
        if o.get("channel") == "loadtest":
            out["loadtest"] += 1
            continue
        if o["id"] in seen:
            out["duplicates"] += 1
            continue
        seen.add(o["id"])
        if o["customer_id"] not in people:
            out["dlq"].append((o["id"], "unknown customer"))
            continue
        out["clean"][o["id"]] = priced(o, people[o["customer_id"]])
    return out


def counter(rows, stream, label, name):
    return sum(r.get(name, 0) for r in rows if r["stream"] == stream and r["label"] == label)


def ingest_all(run_id, rows):
    for chunk in data.chunks(rows):
        assert sources.ingest(json.dumps(chunk)) == 200
    assert sources.ingest(data.malformed(run_id)) == 200


def of_run(records, run_id):
    return [r for r in records if r["value"].get("run_id") == run_id or f'"{run_id}' in (r["value"].get("payload") or "")]


def wait_for(fn, ok, tries=20):
    value = fn()
    while not ok(value) and tries > 0:
        time.sleep(0.5)
        value = fn()
        tries -= 1
    return value


class SeededRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_id = "test-" + str(time.time_ns())
        cls.rows = data.orders(cls.run_id, seed=11)
        cls.exp = expected(cls.rows)
        cls.before = sources.counters()
        ingest_all(cls.run_id, cls.rows)
        n_dlq = len(cls.exp["dlq"]) + 1
        cls.clean = wait_for(lambda: of_run(sources.topic("orders-clean"), cls.run_id), lambda v: len(v) >= len(cls.exp["clean"]))
        cls.dlq = wait_for(lambda: of_run(sources.topic("orders-dlq"), cls.run_id), lambda v: len(v) >= n_dlq)
        cls.table = wait_for(lambda: sources.orders_table(cls.run_id), lambda v: len(v) >= len(cls.exp["clean"]))
        cls.after = sources.counters()

    def test_the_seeded_input_covers_every_path(self):
        self.assertGreaterEqual(len(self.exp["clean"]), 60)
        self.assertGreater(self.exp["duplicates"], 0)
        self.assertGreater(self.exp["loadtest"], 0)
        self.assertGreater(self.exp["invalid"], 10)
        self.assertTrue(any(r == "unknown customer" for _, r in self.exp["dlq"]))
        self.assertTrue(any(v["priority"] == "high" for v in self.exp["clean"].values()))
        self.assertTrue(any(v["priority"] == "normal" for v in self.exp["clean"].values()))

    def test_clean_topic_has_each_valid_order_once_enriched_and_priced(self):
        got = {r["value"]["id"]: r["value"] for r in self.clean}
        self.assertEqual(len(self.clean), len(got), "an order id reached the clean topic twice")
        self.assertEqual(got, self.exp["clean"])

    def test_clean_topic_is_keyed_by_order_id_so_an_order_always_lands_on_one_partition(self):
        for r in self.clean:
            self.assertEqual(r["key"], r["value"]["id"])
        self.assertGreater(len({r["partition"] for r in self.clean}), 1)

    def test_dead_letter_topic_has_every_invalid_record_with_its_first_broken_rule(self):
        envelopes = [r["value"] for r in self.dlq if "broken" not in r["value"]["payload"]]
        got = sorted((e["id"] or "", e["error"]) for e in envelopes)
        want = sorted((i or "", r) for i, r in self.exp["dlq"])
        self.assertEqual(len(got), len(want))
        for (gid, gerr), (wid, wreason) in zip(got, want):
            self.assertEqual(gid, wid)
            self.assertIn(wreason, gerr)
        for e in envelopes:
            original = json.loads(e["payload"])
            self.assertEqual(original["run_id"], self.run_id)

    def test_a_body_that_is_not_json_goes_to_the_dead_letter_topic_as_raw_bytes(self):
        broken = [r["value"] for r in self.dlq if "broken" in r["value"]["payload"]]
        self.assertEqual(len(broken), 1)
        self.assertEqual(broken[0]["payload"], data.malformed(self.run_id))
        self.assertIn("JSON array", broken[0]["error"])

    def test_postgres_sink_has_the_same_rows_as_the_clean_topic(self):
        got = {r["id"]: r for r in self.table}
        self.assertEqual(got, self.exp["clean"])

    def test_priority_file_has_exactly_the_high_value_orders(self):
        got = {r["id"]: r for r in sources.priority_file(self.run_id)}
        want = {k: v for k, v in self.exp["clean"].items() if v["priority"] == "high"}
        self.assertEqual(got, want)

    def test_metrics_count_what_each_step_did(self):
        def delta(stream, label, name):
            return counter(self.after, stream, label, name) - counter(self.before, stream, label, name)

        self.assertEqual(delta("orders", "validate", "error"), self.exp["invalid"])
        self.assertEqual(delta("orders", "drop_loadtest", "received") - delta("orders", "drop_loadtest", "sent"), self.exp["loadtest"])
        self.assertEqual(delta("orders", "dedupe_by_id", "received") - delta("orders", "dedupe_by_id", "sent"), self.exp["duplicates"])
        self.assertEqual(delta("orders", "split_batch", "error"), 1)
        self.assertEqual(delta("orders", "clean_topic", "sent"), len(self.exp["clean"]))
        self.assertEqual(delta("orders", "postgres_orders", "sent"), len(self.exp["clean"]))
        self.assertEqual(delta("orders", "dead_letter_topic", "sent"), len(self.exp["dlq"]) + 1)
        high = sum(1 for v in self.exp["clean"].values() if v["priority"] == "high")
        self.assertEqual(delta("orders", "priority_file", "sent"), high)


class DedupeTest(unittest.TestCase):
    def base(self, run_id, qty):
        return {"id": f"{run_id}-x", "run_id": run_id, "customer_id": "c004", "sku": "SKU-01", "qty": qty,
                "unit_price_cents": 1000, "email": "d@mail.com", "country": "US", "channel": "web"}

    def test_a_rejected_record_does_not_block_a_later_valid_record_with_the_same_id(self):
        run_id = "dedupe-" + str(time.time_ns())
        self.assertEqual(sources.ingest(json.dumps([self.base(run_id, 0)])), 200)
        self.assertEqual(sources.ingest(json.dumps([self.base(run_id, 2)])), 200)
        rows = wait_for(lambda: sources.orders_table(run_id), lambda v: len(v) >= 1)
        self.assertEqual([(r["id"], r["qty"], r["net_cents"]) for r in rows], [(f"{run_id}-x", 2, 1800)])

    def test_a_resent_order_in_a_later_request_is_dropped_and_the_first_version_wins(self):
        run_id = "resend-" + str(time.time_ns())
        self.assertEqual(sources.ingest(json.dumps([self.base(run_id, 3)])), 200)
        self.assertEqual(sources.ingest(json.dumps([self.base(run_id, 9)])), 200)
        time.sleep(1.5)
        rows = sources.orders_table(run_id)
        self.assertEqual([(r["qty"], r["net_cents"]) for r in rows], [(3, 2700)])
        clean = of_run(sources.topic("orders-clean"), run_id)
        self.assertEqual([r["value"]["qty"] for r in clean], [3])


class PipelinesTest(unittest.TestCase):
    def test_file_input_loaded_every_customer_from_the_csv_normalized(self):
        want = [{"id": r["id"], "name": r["name"], "tier": r["tier"], "country": r["country"]} for r in customers_from_csv().values()]
        self.assertEqual(sources.customers_table(), sorted(want, key=lambda r: r["id"]))

    def test_both_streams_run_in_one_connect_process(self):
        s = sources.streams()
        self.assertEqual(set(s), {"orders", "customers"})
        self.assertTrue(s["orders"]["active"])
        self.assertFalse(s["customers"]["active"], "the csv stream should end after reading its file")

    def test_ui_serves_every_tab_and_api(self):
        with urllib.request.urlopen(f"{UI}/", timeout=10) as r:
            html = r.read().decode()
        for tab in ["pipelines", "metrics", "outputs"]:
            self.assertIn(f'data-tab="{tab}"', html)
        with urllib.request.urlopen(f"{UI}/api/pipelines", timeout=10) as r:
            files = json.load(r)["files"]
        self.assertIn("pipelines/orders.yaml", files)
        self.assertIn("rules/validate_order.blobl", files)


if __name__ == "__main__":
    unittest.main()
