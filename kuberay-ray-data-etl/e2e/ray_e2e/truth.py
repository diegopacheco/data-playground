from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

type Key = tuple[str, str]


@dataclass(frozen=True)
class Aggregate:
    events: int
    amount_cents: int
    max_amount_cents: int


def is_valid(event: Mapping[str, Any]) -> bool:
    return int(event["amount_cents"]) > 0


def category(event: Mapping[str, Any]) -> str:
    return str(event["category"]).strip().lower()


def expected_aggregates(events: Iterable[Mapping[str, Any]]) -> dict[Key, Aggregate]:
    groups: dict[Key, Aggregate] = {}
    for event in events:
        if not is_valid(event):
            continue
        key = (str(event["batch_id"]), category(event))
        amount = int(event["amount_cents"])
        old = groups.get(key, Aggregate(0, 0, 0))
        groups[key] = Aggregate(old.events + 1, old.amount_cents + amount, max(old.max_amount_cents, amount))
    return groups


def expected_event_ids(events: Iterable[Mapping[str, Any]]) -> set[str]:
    return {str(event["event_id"]) for event in events if is_valid(event)}


def duplicates(ids: Iterable[str]) -> list[str]:
    return sorted(i for i, n in Counter(ids).items() if n > 1)


def compare(batch_id: str, events: Sequence[Mapping[str, Any]], output_ids: Sequence[str], output_aggregates: Mapping[Key, Aggregate]) -> list[str]:
    problems = []
    dup = duplicates(output_ids)
    if dup:
        problems.append(f"{batch_id}: {len(dup)} duplicated event ids, first {dup[0]}")
    expected_ids = expected_event_ids(events)
    missing = expected_ids - set(output_ids)
    extra = set(output_ids) - expected_ids
    if missing:
        problems.append(f"{batch_id}: {len(missing)} valid input events missing from output")
    if extra:
        problems.append(f"{batch_id}: {len(extra)} output events not in valid input")
    if output_aggregates != expected_aggregates(events):
        problems.append(f"{batch_id}: aggregates differ from ground truth")
    return problems
