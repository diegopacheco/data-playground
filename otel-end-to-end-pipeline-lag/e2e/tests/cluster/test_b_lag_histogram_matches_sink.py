import time

from harness import kube, pipeline, prometheus
from harness.lag import exact_quantile, from_samples

FRACTION_TOLERANCE = 0.02
MEAN_TOLERANCE_SECONDS = 0.05
SLO_BOUND = 2.0
SPREAD_SLOWDOWN_MS = 1000


def test_lag_histogram_in_prometheus_matches_lag_recomputed_from_postgres_rows() -> None:
    kube.set_consumer_slowdown(SPREAD_SLOWDOWN_MS)
    try:
        warm_id = f"warm-{int(time.time())}"
        pipeline.wait_for_sink(warm_id, pipeline.produce(warm_id, rate=20, seconds=2))
        before = prometheus.stable_lag_histogram()
        run_id = f"lag-{int(time.time())}"
        acked = pipeline.produce(run_id, rate=50, seconds=30)
        rows = pipeline.wait_for_sink(run_id, acked)
        assert len(rows) == acked, "no message may be lost between producer ack and sink"
        after = prometheus.wait_for_count(before.count + acked)
    finally:
        kube.set_consumer_slowdown(0)

    delta = after.minus(before)
    assert delta.count == acked, f"histogram counted {delta.count}, sink has {acked}"

    samples = [r.lag_seconds for r in rows]
    from_sink = from_samples(samples, delta.bounds)
    within_slo = from_sink.fraction_within(SLO_BOUND)
    assert 0 < within_slo < 1, "the run must put messages on both sides of the 2 s SLO bound to prove the bucket matters"

    print(f"\nRESULT lag run={run_id} messages={acked} consumer slowdown={SPREAD_SLOWDOWN_MS}ms per poll batch")
    print(f"  {'le':>6} {'prometheus':>11} {'postgres':>9}")
    for bound in delta.bounds:
        p, s = delta.fraction_within(bound), from_sink.fraction_within(bound)
        print(f"  {bound:>6} {p:>11.4f} {s:>9.4f}")
        assert abs(p - s) <= FRACTION_TOLERANCE, f"bucket le={bound}: prometheus {p:.4f} vs sink {s:.4f}"
    print(f"  mean   prometheus={delta.mean():.4f}s postgres={from_sink.mean():.4f}s")
    for q in (0.5, 0.95, 0.99):
        print(f"  p{int(q * 100):<3} prometheus={delta.quantile(q):.4f}s postgres_exact={exact_quantile(samples, q):.4f}s")
    assert abs(delta.mean() - from_sink.mean()) <= MEAN_TOLERANCE_SECONDS
