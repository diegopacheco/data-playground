import pytest

from streambench.config import BenchConfig
from streambench.order import OrderTracker
from streambench.pacer import due
from streambench.payload import MIN_SIZE, encode, decode, now_us
from streambench.recorder import Recorder
from streambench.stats import percentile, summarize


def feed(tracker: OrderTracker, seqs: list[int]) -> None:
    for seq in seqs:
        tracker.observe(seq % tracker.partitions, seq)


def test_payload_carries_seq_and_send_timestamp_and_has_the_exact_wire_size():
    data = encode(42, 1_794_000_000_123_456, 1024)
    assert len(data) == 1024
    stamp = decode(data)
    assert (stamp.seq, stamp.sent_at_us) == (42, 1_794_000_000_123_456)


def test_payload_smaller_than_header_is_refused_so_no_run_silently_drops_the_timestamp():
    with pytest.raises(ValueError):
        encode(1, 1, MIN_SIZE - 1)


def test_every_message_once_in_order_is_complete():
    tracker = OrderTracker(3)
    feed(tracker, list(range(10)))
    assert tracker.in_order()
    assert tracker.complete(10)


def test_a_lost_message_is_a_gap_and_the_run_is_not_complete():
    tracker = OrderTracker(3)
    feed(tracker, [0, 1, 2, 4, 5, 6, 7, 8, 9])
    assert tracker.gaps == 1
    assert not tracker.complete(10)


def test_a_duplicate_or_reordered_message_is_caught_even_when_the_count_matches():
    tracker = OrderTracker(3)
    feed(tracker, [0, 1, 2, 6, 3, 4, 5, 7, 8, 9])
    assert tracker.backwards == 1
    assert not tracker.complete(10)


def test_messages_interleaved_across_partitions_are_still_in_order_per_partition():
    tracker = OrderTracker(3)
    feed(tracker, [2, 0, 5, 1, 3, 8, 4, 6, 7, 9])
    assert tracker.complete(10)


def test_message_on_the_wrong_partition_is_misrouted():
    tracker = OrderTracker(3)
    tracker.observe(0, 1)
    assert tracker.misrouted == 1
    assert not tracker.in_order()


def test_missing_tail_messages_fail_completeness_even_without_gaps():
    tracker = OrderTracker(3)
    feed(tracker, list(range(8)))
    assert tracker.in_order()
    assert not tracker.complete(10)


def test_nearest_rank_percentiles():
    values = list(range(1, 101))
    assert percentile(values, 50) == 50
    assert percentile(values, 99) == 99
    assert percentile([7], 99) == 7
    summary = summarize([3000, 1000, 2000, 4000])
    assert (summary.p50_ms, summary.max_ms, summary.samples) == (2.0, 4.0, 4)


def test_latency_is_receive_time_minus_the_send_timestamp_written_in_the_payload():
    recorder = Recorder(1, 0, 1)
    sent_at = now_us() - 5_000
    recorder.observe(0, encode(0, sent_at, 100), sent_at + 1_000, sent_at + 5_000)
    assert recorder.latencies_us == [5_000]
    assert recorder.ts_violations == 0


def test_broker_timestamp_outside_send_and_receive_is_flagged():
    recorder = Recorder(1, 0, 1)
    recorder.observe(0, encode(0, 1_000, 100), 500, 2_000)
    recorder.observe(0, encode(1, 1_000, 100), 3_000, 2_000)
    assert recorder.ts_violations == 2


def test_millisecond_broker_clock_is_compared_at_millisecond_granularity():
    recorder = Recorder(1, 0, 1000)
    recorder.observe(0, encode(0, 1_000_700, 100), 1_000_000, 1_001_200)
    assert recorder.ts_violations == 0


def test_warmup_messages_count_for_completeness_but_not_for_latency():
    recorder = Recorder(1, 10_000, 1)
    recorder.observe(0, encode(0, 9_000, 100), 9_500, 9_900)
    recorder.observe(0, encode(1, 10_000, 100), 10_100, 10_300)
    assert recorder.received == 2
    assert recorder.latencies_us == [300]


def test_pacer_keeps_the_fixed_rate_and_caps_bursts():
    assert due(0.5, 1000, 0, 1000) == 500
    assert due(0.5, 1000, 500, 1000) == 0
    assert due(10.0, 1000, 0, 200) == 200
    assert due(0.0, 0, 0, 300) == 300


def test_config_reads_the_broker_address_for_the_selected_broker():
    cfg = BenchConfig.from_env({"BROKER": "kafka", "KAFKA_BOOTSTRAP": "kafka:9092", "TOPIC": "t", "RATE": "5000"})
    assert (cfg.address, cfg.rate, cfg.partitions) == ("kafka:9092", 5000, 3)
    with pytest.raises(ValueError):
        BenchConfig.from_env({"BROKER": "pulsar", "TOPIC": "t"})
