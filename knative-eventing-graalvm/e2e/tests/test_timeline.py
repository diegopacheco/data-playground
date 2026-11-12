import pytest

from coldstart.timeline import ColdStart, cold_start, median, p95, warm_latency_ms


def record(produced: int, started: int, ready: int, handled: int) -> dict[str, int | str]:
    return {"id": "o", "producedAtMs": produced, "startedAtMs": started, "readyAtMs": ready, "handledAtMs": handled}


def test_cold_start_splits_into_scale_up_app_start_and_first_request() -> None:
    assert cold_start(record(1000, 1700, 1750, 1790)) == ColdStart(790, 700, 50, 40)


def test_a_process_that_started_before_the_event_is_never_counted_as_a_cold_start() -> None:
    with pytest.raises(ValueError):
        cold_start(record(1000, 900, 950, 1010))


def test_warm_latency_is_event_produced_to_handled() -> None:
    assert warm_latency_ms(record(1000, 1, 2, 1012)) == 12


def test_p95_is_nearest_rank_so_it_is_always_an_observed_value() -> None:
    values = [float(v) for v in range(1, 21)]
    assert p95(values) == 19.0
    assert p95([5.0, 1.0, 9.0, 3.0, 7.0]) == 9.0
    assert median([5.0, 1.0, 9.0, 3.0]) == 4.0
