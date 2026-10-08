import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "etl"))

from revenue import aggregate, clean


def row(order_id, category, quantity, price):
    return {"order_id": order_id, "category": category, "quantity": quantity, "price": price}


class CleanTest(unittest.TestCase):
    def test_bad_rows_never_reach_revenue(self):
        rows = [
            row("1", " Toys ", "2", "10.00"),
            row("1", "toys", "2", "10.00"),
            row("2", "toys", "0", "5.00"),
            row("3", "toys", "x", "5.00"),
            row("4", "", "1", "5.00"),
            row("5", "books", "1", "-1"),
        ]
        cleaned = clean(rows)
        self.assertEqual([r["order_id"] for r in cleaned], ["1"])
        self.assertEqual(cleaned[0]["category"], "toys")


class AggregateTest(unittest.TestCase):
    def test_revenue_is_exact_to_the_cent(self):
        rows = clean([row(str(i), "books", "3", "0.10") for i in range(10)])
        self.assertEqual(aggregate(rows), [{"category": "books", "orders": 10, "units": 30, "revenue": "3.00"}])

    def test_one_line_per_category_sorted(self):
        rows = clean([row("1", "toys", "1", "2.50"), row("2", "books", "2", "1.25"), row("3", "toys", "3", "1.00")])
        self.assertEqual(aggregate(rows), [
            {"category": "books", "orders": 1, "units": 2, "revenue": "2.50"},
            {"category": "toys", "orders": 2, "units": 4, "revenue": "5.50"},
        ])


if __name__ == "__main__":
    unittest.main()
