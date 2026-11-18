import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SweepPoint:
    events: int
    p50_ms: int
    p95_ms: int
    max_ms: int
    snapshots_per_min: float
    files_per_min: float
    avg_file_kb: float
    rows_per_snapshot: float


def percentile(values: list[int], q: float) -> int:
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def duplicate_epochs(snapshots: list[dict[str, Any]]) -> list[tuple[str, int]]:
    seen: set[tuple[str, int]] = set()
    duplicates: list[tuple[str, int]] = []
    for s in snapshots:
        key = (s["query_id"], s["epoch"])
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    return duplicates


def summarize(latencies: list[dict[str, Any]], snapshots: list[dict[str, Any]], start_ms: int, end_ms: int) -> SweepPoint:
    window = [r["commit_ms"] - r["event_ms"] for r in latencies if start_ms <= r["event_ms"] < end_ms]
    commits = [s for s in snapshots if start_ms <= s["commit_ms"] < end_ms]
    minutes = (end_ms - start_ms) / 60_000
    files = sum(s["files"] for s in commits)
    size = sum(s["bytes"] for s in commits)
    records = sum(s["records"] for s in commits)
    return SweepPoint(
        events=len(window),
        p50_ms=percentile(window, 0.5),
        p95_ms=percentile(window, 0.95),
        max_ms=max(window),
        snapshots_per_min=round(len(commits) / minutes, 1),
        files_per_min=round(files / minutes, 1),
        avg_file_kb=round(size / files / 1024, 1) if files else 0.0,
        rows_per_snapshot=round(records / len(commits), 1) if commits else 0.0,
    )
