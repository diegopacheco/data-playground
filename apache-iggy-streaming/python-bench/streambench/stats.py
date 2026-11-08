from dataclasses import dataclass


@dataclass(frozen=True)
class LatencySummary:
    samples: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


def percentile(sorted_values: list[int], pct: float) -> int:
    if not sorted_values:
        raise ValueError("no samples")
    rank = max(1, -(-len(sorted_values) * pct // 100))
    return sorted_values[int(rank) - 1]


def summarize(latencies_us: list[int]) -> LatencySummary:
    values = sorted(latencies_us)
    return LatencySummary(
        samples=len(values),
        p50_ms=percentile(values, 50) / 1000,
        p95_ms=percentile(values, 95) / 1000,
        p99_ms=percentile(values, 99) / 1000,
        max_ms=values[-1] / 1000,
    )
