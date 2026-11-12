import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ColdStart:
    total_ms: int
    scale_up_ms: int
    app_start_ms: int
    first_request_ms: int


def cold_start(record: dict[str, Any]) -> ColdStart:
    produced = record["producedAtMs"]
    started, ready, handled = record["startedAtMs"], record["readyAtMs"], record["handledAtMs"]
    if not produced <= started <= ready <= handled:
        raise ValueError(f"record {record['id']} is not a cold start: {produced=} {started=} {ready=} {handled=}")
    return ColdStart(
        total_ms=handled - produced,
        scale_up_ms=started - produced,
        app_start_ms=ready - started,
        first_request_ms=handled - ready,
    )


def warm_latency_ms(record: dict[str, Any]) -> int:
    return record["handledAtMs"] - record["producedAtMs"]


def median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def p95(values: Sequence[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]
