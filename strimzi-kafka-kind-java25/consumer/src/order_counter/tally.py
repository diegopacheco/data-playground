import json
from dataclasses import dataclass, field
from typing import TypedDict


class Summary(TypedDict):
    run: str
    received: int
    distinct: int


@dataclass
class RunCount:
    received: int = 0
    keys: set[str] = field(default_factory=set)


def parse_run_id(value: bytes | None) -> str | None:
    if value is None:
        return None
    try:
        order = json.loads(value)
    except ValueError:
        return None
    run_id = order.get("runId") if isinstance(order, dict) else None
    return run_id if isinstance(run_id, str) and run_id else None


class Tally:
    def __init__(self) -> None:
        self._runs: dict[str, RunCount] = {}
        self._changed: set[str] = set()

    def record(self, run_id: str, key: str) -> None:
        count = self._runs.setdefault(run_id, RunCount())
        count.received += 1
        count.keys.add(key)
        self._changed.add(run_id)

    def drain(self) -> list[Summary]:
        summaries = [self.summary(run_id) for run_id in sorted(self._changed)]
        self._changed.clear()
        return summaries

    def summary(self, run_id: str) -> Summary:
        count = self._runs.get(run_id, RunCount())
        return Summary(run=run_id, received=count.received, distinct=len(count.keys))
