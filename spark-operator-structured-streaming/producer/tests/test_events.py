import json

from eventgen.events import due, event


def test_every_event_id_is_unique_per_producer_run_so_duplicates_in_iceberg_are_detectable() -> None:
    ids = {event("p-abc", seq, 0).id for seq in range(1000)}
    assert len(ids) == 1000
    assert event("p-abc", 3, 0).id != event("p-def", 3, 0).id


def test_the_payload_carries_the_event_time_the_spark_jobs_measure_latency_from() -> None:
    payload = json.loads(event("p", 7, 1767225600123).encode())
    assert payload == {"id": "p-7", "seq": 7, "event_time_ms": 1767225600123}


def test_sends_are_scheduled_from_the_start_so_a_slow_send_does_not_lower_the_rate() -> None:
    assert due(100.0, 0, 50) == 100.0
    assert due(100.0, 50, 50) == 101.0
    assert due(100.0, 500, 50) == 110.0
