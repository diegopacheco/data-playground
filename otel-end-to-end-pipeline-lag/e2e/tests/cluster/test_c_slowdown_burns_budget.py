import time
from collections.abc import Callable

from harness import kube, pipeline, prometheus

FAST_BURN = "PipelineFreshnessFastBurn"
SLOWDOWN_MS = 2500
RATE = 50


def wait_until(check: Callable[[], bool], timeout: float, step: float = 2) -> float:
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        if check():
            return time.monotonic() - started
        time.sleep(step)
    raise AssertionError(f"condition not met within {timeout}s")


def burn(window: str) -> float:
    return prometheus.scalar(f"pipeline:slo_burn_rate:{window}") or 0.0


def test_consumer_slowdown_fires_fast_burn_alert_and_removing_it_recovers() -> None:
    run_id = f"slo-{int(time.time())}"
    pipeline.start(run_id, RATE)
    try:
        time.sleep(60)
        wait_until(lambda: burn("1m") < 1 and not prometheus.firing(FAST_BURN), timeout=180)
        healthy_burn = burn("1m")

        injected = time.monotonic()
        kube.set_consumer_slowdown(SLOWDOWN_MS)
        peak_burn = 0.0
        peak_group_lag = 0.0

        def fast_burn_firing() -> bool:
            nonlocal peak_burn, peak_group_lag
            peak_burn = max(peak_burn, burn("1m"))
            peak_group_lag = max(peak_group_lag, prometheus.scalar("pipeline:consumer_group_lag:sum") or 0.0)
            return prometheus.firing(FAST_BURN)

        wait_until(fast_burn_firing, timeout=180)
        fired_after = time.monotonic() - injected
        p99_slow = prometheus.scalar("pipeline:lag_seconds:p99_1m") or 0.0
        attainment_slow = prometheus.scalar("pipeline:slo_attainment:ratio_rate5m") or 0.0
        budget_slow = prometheus.scalar("pipeline:slo_error_budget_remaining:ratio_rate5m") or 0.0

        removed = time.monotonic()
        kube.set_consumer_slowdown(0)
        wait_until(lambda: not prometheus.firing(FAST_BURN) and burn("30s") < 1, timeout=240)
        recovered_after = time.monotonic() - removed
        p99_recovered = prometheus.scalar("pipeline:lag_seconds:p99_1m") or 0.0
    finally:
        acked = pipeline.stop(run_id)

    rows = pipeline.wait_for_sink(run_id, acked)
    assert len(rows) == acked, "slowdown and two consumer restarts must not lose messages"
    late = sum(1 for r in rows if r.lag_seconds > 2)

    print(f"\nRESULT slo run={run_id} rate={RATE}/s slowdown={SLOWDOWN_MS}ms per poll batch")
    print(f"  healthy burn rate 1m           {healthy_burn:.2f}x")
    print(f"  fast burn alert firing after   {fired_after:.0f}s")
    print(f"  peak burn rate 1m              {peak_burn:.1f}x")
    print(f"  peak consumer group lag        {peak_group_lag:.0f} messages")
    print(f"  p99 lag while slowed           {p99_slow:.2f}s")
    print(f"  5m attainment while slowed     {attainment_slow:.4f}")
    print(f"  5m error budget left           {budget_slow:.2f}")
    print(f"  alert resolved after removal   {recovered_after:.0f}s")
    print(f"  p99 lag after recovery         {p99_recovered:.2f}s")
    print(f"  messages {acked}, late over 2s {late}, lost {acked - len(rows)}")
