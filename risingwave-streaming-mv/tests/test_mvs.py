import json
import os
import sys
import unittest
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
import data
import kafka_io
import scenario

UI = os.environ.get("UI_URL", "http://localhost:8080")


def get(path):
    with urllib.request.urlopen(UI + path, timeout=60) as r:
        return r.read().decode()


def minute(ts):
    return ts[:16] + ":00"


def inputs(d, corrected):
    customers = {c["customer_id"]: dict(c) for c in d["customers"]}
    orders = {o["order_id"]: o for o in d["orders"]}
    payments = list(d["payments"])
    if corrected:
        c = d["corrections"]
        customers[c["moved_customer"]["customer_id"]]["region"] = c["moved_customer"]["region"]
        for o in c["updated_orders"] + c["late_orders"]:
            orders[o["order_id"]] = o
        payments += c["late_payments"]
    return customers, orders, payments


def grouped(rows, key_fields):
    groups = defaultdict(lambda: {"orders": 0, "revenue_cents": 0})
    for key, amount in rows:
        groups[key]["orders"] += 1
        groups[key]["revenue_cents"] += amount
    return [dict(zip(key_fields, k if isinstance(k, tuple) else (k,)), **v) for k, v in sorted(groups.items())]


def expected(d, corrected):
    customers, orders, payments = inputs(d, corrected)
    ordered = [orders[i] for i in sorted(orders)]
    enriched = [{
        "order_id": o["order_id"], "customer_id": o["customer_id"],
        "name": customers[o["customer_id"]]["name"], "region": customers[o["customer_id"]]["region"],
        "product": o["product"], "amount_cents": o["amount_cents"], "event_time": o["event_time"],
    } for o in ordered]
    paid = defaultdict(list)
    for p in payments:
        paid[p["order_id"]].append(p["paid_cents"])
    return {
        "mv_revenue_per_minute": grouped([(minute(o["event_time"]), o["amount_cents"]) for o in ordered], ["window_start"]),
        "mv_orders_enriched": enriched,
        "mv_region_revenue": grouped([(e["region"], e["amount_cents"]) for e in enriched], ["region"]),
        "mv_region_minute": grouped([((e["region"], minute(e["event_time"])), e["amount_cents"]) for e in enriched], ["region", "window_start"]),
        "mv_order_payments": [{
            "order_id": o["order_id"], "amount_cents": o["amount_cents"], "payments": len(paid[o["order_id"]]),
            "paid_cents": sum(paid[o["order_id"]]), "due_cents": o["amount_cents"] - sum(paid[o["order_id"]]),
        } for o in ordered if paid[o["order_id"]]],
    }


def by(rows, *fields):
    return {tuple(r[f] for f in fields): r for r in rows}


class MaterializedViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = data.build()
        snaps = json.loads(get("/api/snapshots"))
        assert snaps["phase"] == "done", f"run-all did not finish, phase is {snaps['phase']}"
        cls.before = snaps["before"]
        cls.after = snaps["after"]
        cls.live = scenario.snapshot()

    def test_every_mv_equals_the_answer_computed_from_the_base_input(self):
        want = expected(self.d, corrected=False)
        for name, rows in want.items():
            with self.subTest(mv=name):
                self.assertEqual(self.before[name], rows)

    def test_every_mv_equals_the_answer_computed_after_late_and_updated_rows(self):
        want = expected(self.d, corrected=True)
        for name, rows in want.items():
            with self.subTest(mv=name):
                self.assertEqual(self.after[name], rows)
                self.assertEqual(self.live[name], rows)

    def test_late_orders_reopen_only_the_old_windows_they_belong_to(self):
        c = self.d["corrections"]
        touched = {minute(o["event_time"]) for o in c["late_orders"] + c["updated_orders"]}
        before = by(self.before["mv_revenue_per_minute"], "window_start")
        after = by(self.after["mv_revenue_per_minute"], "window_start")
        changed = {k[0] for k in after if after[k] != before.get(k)}
        self.assertEqual(changed, touched)
        self.assertTrue(all(minute(o["event_time"]) < "2026-10-01 12:03:00" for o in c["late_orders"]))
        late_per_window = defaultdict(int)
        for o in c["late_orders"]:
            late_per_window[minute(o["event_time"])] += 1
        for window, count in late_per_window.items():
            self.assertEqual(after[(window,)]["orders"] - before[(window,)]["orders"], count)

    def test_an_updated_order_overwrites_its_row_instead_of_adding_one(self):
        c = self.d["corrections"]
        total_orders = len(self.d["orders"]) + len(c["late_orders"])
        self.assertEqual(sum(r["orders"] for r in self.after["mv_revenue_per_minute"]), total_orders)
        enriched = by(self.after["mv_orders_enriched"], "order_id")
        for o in c["updated_orders"]:
            old = next(b for b in self.d["orders"] if b["order_id"] == o["order_id"])
            self.assertNotEqual(o["amount_cents"], old["amount_cents"])
            self.assertEqual(enriched[(o["order_id"],)]["amount_cents"], o["amount_cents"])
        self.assertEqual(scenario.query("SELECT count(*) AS n FROM orders WHERE version = 2")[0]["n"], len(c["updated_orders"]))

    def test_moving_a_customer_moves_its_revenue_through_the_join_and_the_cascade(self):
        moved = self.d["corrections"]["moved_customer"]
        old_region = next(c["region"] for c in self.d["customers"] if c["customer_id"] == moved["customer_id"])
        self.assertNotEqual(old_region, moved["region"])
        _, orders, _ = inputs(self.d, corrected=True)
        moved_cents = sum(o["amount_cents"] for o in orders.values() if o["customer_id"] == moved["customer_id"])
        self.assertGreater(moved_cents, 0)
        after = by(self.after["mv_region_revenue"], "region")
        regions = {r["region"] for r in self.after["mv_orders_enriched"] if r["customer_id"] == moved["customer_id"]}
        self.assertEqual(regions, {moved["region"]})
        others = [o for o in orders.values() if o["customer_id"] != moved["customer_id"]]
        old_region_customers = {c["customer_id"] for c in self.d["customers"] if c["region"] == old_region}
        self.assertEqual(after.get((old_region,), {"revenue_cents": 0})["revenue_cents"],
                         sum(o["amount_cents"] for o in others if o["customer_id"] in old_region_customers))

    def test_a_late_payment_joins_an_order_that_was_unpaid(self):
        late = self.d["corrections"]["late_payments"]
        before = by(self.before["mv_order_payments"], "order_id")
        after = by(self.after["mv_order_payments"], "order_id")
        self.assertTrue(late)
        for p in late:
            self.assertNotIn((p["order_id"],), before)
            self.assertEqual(after[(p["order_id"],)]["due_cents"], 0)

    def test_cascading_mv_equals_an_aggregation_of_its_parent_mv(self):
        parent = grouped([(r["region"], r["amount_cents"]) for r in self.live["mv_orders_enriched"]], ["region"])
        self.assertEqual(self.live["mv_region_revenue"], parent)

    def test_sink_topic_streams_every_change_and_compacts_to_the_final_answer(self):
        records = kafka_io.read_topic("region_revenue")
        want = expected(self.d, corrected=True)["mv_region_revenue"]
        self.assertEqual(sorted(kafka_io.compact(records), key=lambda r: r["region"]), want)
        base = by(expected(self.d, corrected=False)["mv_region_revenue"], "region")
        values = [r["value"] for r in records if r["value"]]
        for region, row in base.items():
            if row != by(want, "region").get(region):
                self.assertIn(row, values)

    def test_ui_page_has_every_tab(self):
        page = get("/")
        for tab in ["Pipeline", "Windows", "Joins", "Cascade and Sink", "Corrections"]:
            self.assertIn(tab, page)


if __name__ == "__main__":
    unittest.main()
