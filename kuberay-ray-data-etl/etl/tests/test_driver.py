from etl.driver import next_to_start


def test_in_flight_batches_are_not_started_twice() -> None:
    assert next_to_start(["a", "b", "c"], {"a"}, 3) == ["b", "c"]


def test_no_more_than_capacity_batches_run_at_once() -> None:
    assert next_to_start(["a", "b", "c", "d"], {"x"}, 3) == ["a", "b"]
    assert next_to_start(["a"], {"x", "y", "z"}, 3) == []
