import pyarrow as pa

from i36_pipeline import revenue


def orders(rows):
    names = ["order_id", "customer", "product", "category", "quantity", "price", "ts"]
    return pa.Table.from_pylist([dict(zip(names, r)) for r in rows], schema=pa.schema(list(revenue.RAW_TYPES.items())))


def test_clean_drops_orders_that_would_distort_revenue():
    raw = orders([
        (1, "a", "p", "toys", 2, 10.0, "t"),
        (2, "b", "p", "toys", 0, 10.0, "t"),
        (3, "c", "p", "toys", 1, -5.0, "t"),
        (1, "a", "p", "toys", 2, 10.0, "t"),
        (4, "d", "p", None, 1, 3.0, "t"),
    ])
    cleaned = revenue.clean(raw)
    assert cleaned["order_id"].to_pylist() == [1]
    assert cleaned["revenue"].to_pylist() == [20.0]


def test_clean_normalizes_category_so_groups_do_not_split():
    raw = orders([(1, "a", "p", " Toys ", 1, 1.5, "t"), (2, "b", "p", "toys", 1, 2.5, "t")])
    result = revenue.revenue_by_category(revenue.clean(raw)).to_pylist()
    assert result == [{"category": "toys", "orders": 2, "units": 2, "revenue": 4.0}]


def test_revenue_is_quantity_times_price_ordered_by_revenue():
    raw = orders([
        (1, "a", "p", "books", 3, 10.10, "t"),
        (2, "b", "p", "toys", 1, 99.99, "t"),
        (3, "c", "p", "books", 1, 0.01, "t"),
    ])
    result = revenue.revenue_by_category(revenue.clean(raw)).to_pylist()
    assert [r["category"] for r in result] == ["toys", "books"]
    assert result[1] == {"category": "books", "orders": 2, "units": 4, "revenue": 30.31}


def test_full_csv_keeps_every_valid_order():
    cleaned = revenue.clean(revenue.load_raw("/app/data/orders.csv"))
    assert cleaned.num_rows == 200
    assert sum(r["orders"] for r in revenue.revenue_by_category(cleaned).to_pylist()) == 200
