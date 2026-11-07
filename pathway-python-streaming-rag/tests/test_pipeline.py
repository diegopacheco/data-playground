import os
import time
import unittest
import urllib.request

import helpers

TEST_FILE = os.path.join(helpers.ORDERS, "zz-test-orders.csv")
REGIONS_FILE = os.path.join(helpers.REGIONS, "regions.csv")
HEADER = "order_id,region,amount,ts\n"
FREE_SLOTS_FROM = 1893456000 // helpers.WINDOW


def csv_text(rows):
    return HEADER + "".join(f"{o},{r},{a},{t}\n" for o, r, a, t in rows)


class PipelineTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        if os.path.exists(TEST_FILE):
            os.remove(TEST_FILE)
        with open(REGIONS_FILE) as handle:
            self.regions_text = handle.read()
        used = {o["ts"] // helpers.WINDOW for o in helpers.all_orders()}
        slot = FREE_SLOTS_FROM + time.time_ns() // 1000 % 500000 * 4
        while any(s in used for s in range(slot, slot + 4)):
            slot += 4
        self.base = slot * helpers.WINDOW

    def tearDown(self):
        if os.path.exists(TEST_FILE):
            os.remove(TEST_FILE)
        with open(REGIONS_FILE) as handle:
            if handle.read() != self.regions_text:
                helpers.write_atomic(REGIONS_FILE, self.regions_text)
        helpers.converge()

    def assertConverged(self):
        want, got = helpers.converge()
        self.assertEqual(want[1], got[1], "per region totals differ from the independent computation")
        self.assertEqual(want[0], got[0], "tumbling windows differ from the independent computation")
        return got

    def test_aggregates_equal_an_independent_computation_over_files_and_topic(self):
        windows, totals = self.assertConverged()
        self.assertGreaterEqual(len(windows), 15)
        self.assertEqual({"us", "eu", "br", "jp"}, set(totals))

    def test_orders_with_an_unknown_region_are_dropped_by_the_join(self):
        _, totals = self.assertConverged()
        known = sum(1 for o in helpers.all_orders() if o["region"] in helpers.regions())
        unknown = sum(1 for o in helpers.all_orders() if o["region"] not in helpers.regions())
        self.assertGreaterEqual(unknown, 1)
        self.assertEqual(known, sum(t["orders"] for t in totals.values()))
        self.assertNotIn("xx", totals)

    def test_a_new_file_lands_in_the_right_windows(self):
        b = self.base
        helpers.write_atomic(TEST_FILE, csv_text([("t-1", "jp", 1000, b + 5), ("t-2", "jp", 3000, b + 59), ("t-3", "jp", 500, b + 60)]))
        windows, _ = self.assertConverged()
        first = windows[("jp", b)]
        second = windows[("jp", b + 60)]
        self.assertEqual((2, 4000, 3000, 4400), (first["orders"], first["revenue"], first["max_amount"], first["gross"]))
        self.assertEqual((1, 500, 550), (second["orders"], second["revenue"], second["gross"]))

    def test_editing_a_row_updates_only_its_window(self):
        b = self.base
        helpers.write_atomic(TEST_FILE, csv_text([("t-1", "eu", 1000, b + 1), ("t-2", "eu", 2000, b + 61)]))
        before, _ = self.assertConverged()
        helpers.write_atomic(TEST_FILE, csv_text([("t-1", "eu", 4000, b + 1), ("t-2", "eu", 2000, b + 61)]))
        after, _ = self.assertConverged()
        self.assertEqual(before[("eu", b)]["revenue"] + 3000, after[("eu", b)]["revenue"])
        self.assertEqual(4800, after[("eu", b)]["gross"])
        self.assertEqual(before[("eu", b + 60)], after[("eu", b + 60)])

    def test_moving_a_row_to_another_window_retracts_it_from_the_old_one(self):
        b = self.base
        helpers.write_atomic(TEST_FILE, csv_text([("t-1", "br", 700, b + 10)]))
        before, _ = self.assertConverged()
        self.assertIn(("br", b), before)
        helpers.write_atomic(TEST_FILE, csv_text([("t-1", "br", 700, b + 130)]))
        after, _ = self.assertConverged()
        self.assertNotIn(("br", b), after)
        self.assertEqual(1, after[("br", b + 120)]["orders"])

    def test_deleting_a_file_retracts_all_its_rows(self):
        before_windows, before_totals = self.assertConverged()
        b = self.base
        helpers.write_atomic(TEST_FILE, csv_text([("t-1", "us", 100, b), ("t-2", "us", 200, b + 1)]))
        self.assertConverged()
        os.remove(TEST_FILE)
        after_windows, after_totals = self.assertConverged()
        self.assertEqual(before_totals, after_totals)
        self.assertEqual(before_windows, after_windows)

    def test_orders_published_to_the_topic_are_aggregated_with_the_file_orders(self):
        b = self.base
        stamp = time.time_ns()
        helpers.kafka_produce([
            {"order_id": f"k-{stamp}-1", "region": "us", "amount": 1500, "ts": b + 2},
            {"order_id": f"k-{stamp}-2", "region": "us", "amount": 2500, "ts": b + 3},
        ])
        helpers.write_atomic(TEST_FILE, csv_text([("t-1", "us", 1000, b + 4)]))
        windows, _ = self.assertConverged()
        mixed = windows[("us", b)]
        self.assertEqual((3, 5000, 2500, 5400), (mixed["orders"], mixed["revenue"], mixed["max_amount"], mixed["gross"]))

    def test_changing_a_tax_rate_recomputes_gross_through_the_join(self):
        _, before = self.assertConverged()
        helpers.write_atomic(REGIONS_FILE, self.regions_text.replace("jp,Japan,10", "jp,Japan,50"))
        _, after = self.assertConverged()
        jp = [o for o in helpers.all_orders() if o["region"] == "jp"]
        self.assertEqual(sum(o["amount"] * 150 // 100 for o in jp), after["jp"]["gross"])
        self.assertEqual(before["jp"]["revenue"], after["jp"]["revenue"])
        self.assertEqual(before["us"], after["us"])

    def test_ui_page_has_every_tab(self):
        with urllib.request.urlopen(helpers.UI + "/", timeout=10) as response:
            page = response.read().decode()
        for tab in ("windows", "totals", "docs", "search"):
            self.assertIn(f'data-tab="{tab}"', page)


if __name__ == "__main__":
    unittest.main()
