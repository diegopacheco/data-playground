from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


@dataclass(frozen=True)
class TimeRange:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Partition:
    index: int
    day: date
    window: TimeRange


def partition_for(start_day: date, index: int) -> Partition:
    if index < 0:
        raise ValueError(f"index must be >= 0, got {index}")
    day = start_day + timedelta(days=index)
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return Partition(index, day, TimeRange(start, start + timedelta(days=1)))


def split(window: TimeRange, parts: int) -> list[TimeRange]:
    if parts < 1:
        raise ValueError(f"parts must be >= 1, got {parts}")
    step = (window.end - window.start) / parts
    bounds = [window.start + step * i for i in range(parts)] + [window.end]
    return [TimeRange(bounds[i], bounds[i + 1]) for i in range(parts)]
