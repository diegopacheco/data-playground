import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Histogram:
    bounds: tuple[float, ...]
    cumulative: tuple[int, ...]
    count: int
    total: float

    def minus(self, earlier: Histogram) -> Histogram:
        if self.bounds != earlier.bounds and earlier.count:
            raise ValueError("bucket bounds differ")
        before = earlier.cumulative if earlier.count else tuple(0 for _ in self.bounds)
        return Histogram(
            bounds=self.bounds,
            cumulative=tuple(a - b for a, b in zip(self.cumulative, before)),
            count=self.count - earlier.count,
            total=self.total - earlier.total,
        )

    def fraction_within(self, bound: float) -> float:
        return self.cumulative[self.bounds.index(bound)] / self.count

    def mean(self) -> float:
        return self.total / self.count

    def quantile(self, q: float) -> float:
        rank = q * self.count
        lower_bound, lower_count = 0.0, 0
        for bound, cumulative in zip(self.bounds, self.cumulative):
            if cumulative >= rank:
                inside = cumulative - lower_count
                return lower_bound + (bound - lower_bound) * ((rank - lower_count) / inside if inside else 0)
            lower_bound, lower_count = bound, cumulative
        return math.inf


def from_samples(samples: list[float], bounds: tuple[float, ...]) -> Histogram:
    return Histogram(
        bounds=bounds,
        cumulative=tuple(sum(1 for s in samples if s <= b) for b in bounds),
        count=len(samples),
        total=sum(samples),
    )


def exact_quantile(samples: list[float], q: float) -> float:
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]
