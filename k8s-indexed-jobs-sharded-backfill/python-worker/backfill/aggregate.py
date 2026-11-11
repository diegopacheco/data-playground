from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Stats:
    count: int
    total: int
    min: int
    max: int

    def merge(self, other: Stats) -> Stats:
        return Stats(
            self.count + other.count,
            self.total + other.total,
            min(self.min, other.min),
            max(self.max, other.max),
        )


type Aggregates = dict[str, Stats]


def aggregate(rows: Iterable[tuple[str, int]]) -> Aggregates:
    counts: dict[str, list[int]] = {}
    for category, amount in rows:
        acc = counts.get(category)
        if acc is None:
            counts[category] = [1, amount, amount, amount]
        else:
            acc[0] += 1
            acc[1] += amount
            if amount < acc[2]:
                acc[2] = amount
            if amount > acc[3]:
                acc[3] = amount
    return {c: Stats(a[0], a[1], a[2], a[3]) for c, a in counts.items()}


def merge_all(parts: Iterable[Aggregates]) -> Aggregates:
    merged: Aggregates = {}
    for part in parts:
        for category, stats in part.items():
            current = merged.get(category)
            merged[category] = stats if current is None else current.merge(stats)
    return merged


def row_count(aggregates: Aggregates) -> int:
    return sum(s.count for s in aggregates.values())
