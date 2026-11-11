from datetime import UTC, date, datetime, timedelta

import pytest

from backfill.partition import partition_for, split


def test_every_index_owns_a_distinct_consecutive_day_so_no_two_pods_backfill_the_same_partition() -> None:
    days = [partition_for(date(2026, 10, 1), i).day for i in range(12)]
    assert days == [date(2026, 10, 1) + timedelta(days=i) for i in range(12)]
    assert len(set(days)) == 12


def test_partition_window_is_one_utc_day_half_open() -> None:
    p = partition_for(date(2026, 10, 1), 2)
    assert p.window.start == datetime(2026, 10, 3, tzinfo=UTC)
    assert p.window.end == datetime(2026, 10, 4, tzinfo=UTC)


@pytest.mark.parametrize("parts", [1, 3, 4, 7, 24])
def test_sub_ranges_tile_the_day_without_gaps_or_overlaps_so_each_row_is_read_once(parts: int) -> None:
    window = partition_for(date(2026, 10, 1), 0).window
    ranges = split(window, parts)
    assert len(ranges) == parts
    assert ranges[0].start == window.start
    assert ranges[-1].end == window.end
    for left, right in zip(ranges, ranges[1:]):
        assert left.end == right.start
        assert left.start < left.end


def test_invalid_inputs_fail_loud() -> None:
    with pytest.raises(ValueError):
        partition_for(date(2026, 10, 1), -1)
    with pytest.raises(ValueError):
        split(partition_for(date(2026, 10, 1), 0).window, 0)
