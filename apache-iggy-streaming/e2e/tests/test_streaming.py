from functools import cache
from typing import Any

import pytest

from bench_e2e import config
from bench_e2e.cluster import Run, run_job

RATE = 2000
SECONDS = 5
PAIRS = [(b, c) for b in config.BROKERS for c in config.CLIENTS]


@cache
def short_run(broker: str, client: str) -> dict[str, Any]:
    return run_job(Run(broker, client, RATE, 100, SECONDS))


@pytest.mark.parametrize(("broker", "client"), PAIRS)
def test_every_message_sent_is_received_exactly_once_and_in_order_per_partition(broker: str, client: str):
    result = short_run(broker, client)
    assert result["broker"] == broker and result["client"] == client
    assert result["sent"] >= RATE * SECONDS * 0.95
    assert result["send_errors"] == 0
    assert result["received"] == result["sent"]
    assert (result["gaps"], result["backwards"], result["misrouted"]) == (0, 0, 0)
    assert result["in_order"] and result["complete"]


@pytest.mark.parametrize(("broker", "client"), PAIRS)
def test_latency_comes_from_payload_send_timestamps_that_bracket_the_broker_append_time(broker: str, client: str):
    result = short_run(broker, client)
    assert result["ts_checked"] == result["received"]
    assert result["ts_violations"] == 0
    assert result["run_started_us"] <= result["min_sent_at_us"] <= result["max_sent_at_us"] <= result["run_finished_us"]
    assert result["max_sent_at_us"] - result["min_sent_at_us"] >= (SECONDS - 1) * 1_000_000
    latency = result["latency"]
    assert latency["samples"] >= RATE * (SECONDS - config.WARMUP_SECONDS) * 0.9
    assert 0 < latency["p50_ms"] <= latency["p95_ms"] <= latency["p99_ms"] <= latency["max_ms"]
    assert latency["max_ms"] * 1000 < result["run_finished_us"] - result["run_started_us"]
