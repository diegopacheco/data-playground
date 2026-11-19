from order_counter.tally import Tally, parse_run_id


def test_redelivered_keys_do_not_inflate_the_distinct_count() -> None:
    tally = Tally()
    for key in ("r-0", "r-1", "r-1", "r-2", "r-0"):
        tally.record("r", key)
    assert tally.summary("r") == {"run": "r", "received": 5, "distinct": 3}


def test_runs_are_counted_separately_so_old_data_cannot_hide_a_loss() -> None:
    tally = Tally()
    tally.record("old", "old-0")
    tally.record("new", "new-0")
    tally.record("new", "new-1")
    assert tally.summary("old")["distinct"] == 1
    assert tally.summary("new")["distinct"] == 2


def test_drain_reports_only_runs_that_changed_since_last_drain() -> None:
    tally = Tally()
    tally.record("a", "a-0")
    tally.record("b", "b-0")
    assert [s["run"] for s in tally.drain()] == ["a", "b"]
    assert tally.drain() == []
    tally.record("b", "b-1")
    assert tally.drain() == [{"run": "b", "received": 2, "distinct": 2}]


def test_unknown_run_reports_zero_so_a_missing_run_fails_the_comparison() -> None:
    assert Tally().summary("never") == {"run": "never", "received": 0, "distinct": 0}


def test_run_id_is_read_from_the_order_json() -> None:
    assert parse_run_id(b'{"runId":"roll-1","seq":3}') == "roll-1"


def test_payloads_without_a_run_id_are_not_counted() -> None:
    assert parse_run_id(None) is None
    assert parse_run_id(b"not json") is None
    assert parse_run_id(b"[1,2]") is None
    assert parse_run_id(b'{"runId":""}') is None
    assert parse_run_id(b'{"runId":7}') is None
