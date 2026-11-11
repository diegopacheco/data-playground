from backfill.aggregate import Stats, aggregate, merge_all, row_count

ROWS = [("books", 10), ("games", 5), ("books", 3), ("books", 40), ("games", 7), ("tools", 1)]


def test_aggregate_computes_count_sum_min_max_per_category() -> None:
    assert aggregate(ROWS) == {
        "books": Stats(3, 53, 3, 40),
        "games": Stats(2, 12, 5, 7),
        "tools": Stats(1, 1, 1, 1),
    }


def test_merging_sub_range_results_equals_aggregating_the_whole_partition_so_concurrency_does_not_change_totals() -> None:
    whole = aggregate(ROWS)
    for cut in range(len(ROWS) + 1):
        assert merge_all([aggregate(ROWS[:cut]), aggregate(ROWS[cut:])]) == whole


def test_empty_sub_ranges_do_not_add_categories_or_rows() -> None:
    merged = merge_all([aggregate([]), aggregate(ROWS), aggregate([])])
    assert merged == aggregate(ROWS)
    assert row_count(merged) == len(ROWS)
