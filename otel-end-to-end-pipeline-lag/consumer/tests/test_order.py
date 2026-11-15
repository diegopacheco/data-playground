from lag_consumer.order import BIG_ORDER_CENTS, Order, enrich, lag_seconds, parse

RAW = b'{"id":"r-3","runId":"r","seq":3,"sku":"sku-3","qty":4,"priceCents":211,"eventTimeMs":1700000000123}'


def test_parse_reads_the_event_time_that_lag_is_measured_from() -> None:
    order = parse(RAW)
    assert order == Order("r-3", "r", 3, "sku-3", 4, 211, 1700000000123)


def test_malformed_payloads_are_rejected_instead_of_crashing_the_consumer() -> None:
    assert parse(b"not json") is None
    assert parse(b'{"id":"x"}') is None
    assert parse(b'{"id":"x","runId":"r","seq":"a","sku":"s","qty":1,"priceCents":1,"eventTimeMs":1}') is None


def test_tier_threshold_is_inclusive_so_exactly_200_dollars_is_big() -> None:
    assert enrich(Order("a", "r", 0, "s", 2, BIG_ORDER_CENTS // 2, 0)).tier == "big"
    assert enrich(Order("b", "r", 0, "s", 1, BIG_ORDER_CENTS - 1, 0)).tier == "small"
    assert enrich(Order("c", "r", 0, "s", 3, 211, 0)).total_cents == 633


def test_lag_is_sink_time_minus_event_time_in_seconds() -> None:
    assert abs(lag_seconds(1_000_000, 1_000.75) - 0.75) < 1e-9


def test_clock_skew_never_produces_negative_lag_that_would_hide_slow_messages_in_low_buckets() -> None:
    assert lag_seconds(2_000_000, 1_999.0) == 0.0
