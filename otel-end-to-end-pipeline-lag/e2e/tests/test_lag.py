import pytest

from harness.lag import Histogram, exact_quantile, from_samples

BOUNDS = (0.5, 1.0, 2.0, 5.0)


def test_delta_isolates_one_run_from_everything_counted_before() -> None:
    before = Histogram(BOUNDS, (10, 20, 30, 40), 40, 50.0)
    after = Histogram(BOUNDS, (15, 30, 45, 60), 60, 80.0)
    delta = after.minus(before)
    assert delta == Histogram(BOUNDS, (5, 10, 15, 20), 20, 30.0)


def test_delta_from_an_empty_histogram_is_the_histogram_itself() -> None:
    after = Histogram(BOUNDS, (1, 2, 3, 4), 4, 3.0)
    assert after.minus(Histogram((), (), 0, 0.0)) == after


def test_fraction_within_two_seconds_is_the_slo_good_ratio() -> None:
    hist = from_samples([0.1, 0.4, 1.5, 2.0, 3.0], BOUNDS)
    assert hist.fraction_within(2.0) == pytest.approx(0.8)


def test_samples_on_a_bucket_boundary_count_as_within_it_like_prometheus_le() -> None:
    assert from_samples([1.0], BOUNDS).cumulative == (0, 1, 1, 1)


def test_quantile_interpolates_inside_the_bucket_like_histogram_quantile() -> None:
    hist = Histogram(BOUNDS, (0, 0, 100, 100), 100, 150.0)
    assert hist.quantile(0.5) == pytest.approx(1.5)


def test_exact_quantile_uses_nearest_rank() -> None:
    samples = [float(i) for i in range(1, 101)]
    assert exact_quantile(samples, 0.99) == 99.0
    assert exact_quantile(samples, 0.5) == 50.0
