import pyarrow as pa

from etl.transform import COLUMNS, clean_events


def batch() -> pa.Table:
    return pa.table(
        {
            "event_id": ["a", "b", "c", "d"],
            "batch_id": ["s1-000001"] * 4,
            "user_id": ["user-1", "user-2", "user-1", "user-3"],
            "category": [" Books", "GAMES ", "books", "music"],
            "amount_cents": [100, 0, -5, 250],
            "ts": [1, 1, 1, 1],
            "extra": ["x", "y", "z", "w"],
        }
    )


def test_refunds_and_zero_amounts_are_dropped_so_they_never_reach_revenue_aggregates() -> None:
    assert clean_events(batch())["event_id"].to_pylist() == ["a", "d"]


def test_category_spelling_variants_collapse_into_one_group() -> None:
    assert clean_events(batch())["category"].to_pylist() == ["books", "music"]


def test_output_keeps_only_the_event_contract_columns() -> None:
    assert clean_events(batch()).column_names == COLUMNS
