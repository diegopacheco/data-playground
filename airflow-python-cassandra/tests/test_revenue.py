import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dags"))

import revenue


def order(category, quantity, price):
    return {"category": category, "quantity": str(quantity), "price": str(price)}


class AggregateTest(unittest.TestCase):
    def test_revenue_is_quantity_times_price_not_just_price(self):
        rows = revenue.aggregate([order("books", 3, 10.0)])
        self.assertEqual(rows[0]["total_revenue"], 30.0)

    def test_orders_count_lines_while_quantity_sums_units(self):
        rows = revenue.aggregate([order("toys", 2, 1.0), order("toys", 5, 1.0)])
        self.assertEqual(rows[0]["total_orders"], 2)
        self.assertEqual(rows[0]["total_quantity"], 7)

    def test_revenue_is_rounded_to_cents_after_summing(self):
        rows = revenue.aggregate([order("home", 1, 0.1), order("home", 1, 0.2)])
        self.assertEqual(rows[0]["total_revenue"], 0.3)

    def test_categories_are_kept_apart(self):
        rows = revenue.aggregate([order("books", 1, 5.0), order("toys", 1, 7.0)])
        self.assertEqual({r["category"]: r["total_revenue"] for r in rows}, {"books": 5.0, "toys": 7.0})

    def test_committed_csv_covers_the_six_categories(self):
        rows = revenue.aggregate(revenue.read_orders(ROOT / "data" / "orders.csv"))
        self.assertEqual([r["category"] for r in rows], ["books", "clothing", "electronics", "home", "sports", "toys"])
        self.assertEqual(sum(r["total_orders"] for r in rows), 200)


if __name__ == "__main__":
    unittest.main()
