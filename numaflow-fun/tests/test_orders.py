import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from orders import BIG_ORDER_CENTS, process


def raw(**fields):
    return json.dumps(fields).encode()


class OrdersTest(unittest.TestCase):
    def test_total_is_qty_times_price_so_routing_uses_real_money(self):
        out = process(raw(id="o1", qty=3, price_cents=250))
        self.assertEqual(out["total_cents"], 750)

    def test_threshold_is_inclusive_so_exactly_100_dollars_goes_to_big_sink(self):
        out = process(raw(id="o2", qty=1, price_cents=BIG_ORDER_CENTS))
        self.assertEqual(out["tier"], "big")
        out = process(raw(id="o3", qty=1, price_cents=BIG_ORDER_CENTS - 1))
        self.assertEqual(out["tier"], "small")

    def test_many_cheap_items_can_add_up_to_a_big_order(self):
        out = process(raw(id="o4", qty=100, price_cents=100))
        self.assertEqual(out["tier"], "big")

    def test_original_fields_are_kept_for_downstream_sinks(self):
        out = process(raw(id="o5", qty=1, price_cents=1, customer="ana"))
        self.assertEqual(out["customer"], "ana")

    def test_bad_payloads_are_dropped_instead_of_crashing_the_vertex(self):
        for bad in [b"not json", b"[1,2]", b"\xff\xfe", raw(id="x", qty=0, price_cents=5),
                    raw(id="x", qty=2, price_cents=-1), raw(id="x", qty="2", price_cents=5),
                    raw(qty=1, price_cents=5), raw(id="x", qty=1.5, price_cents=5),
                    raw(id="x", qty=True, price_cents=5)]:
            self.assertIsNone(process(bad), bad)


if __name__ == "__main__":
    unittest.main()
