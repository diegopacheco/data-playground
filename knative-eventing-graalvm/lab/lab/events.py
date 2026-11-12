import json
from collections.abc import Callable
from typing import Any

from lab.store import Store

Headers = list[tuple[str, bytes]]
Sender = Callable[[str, bytes, bytes, Headers], None]


def topic_for(variant: str) -> str:
    return f"orders-{variant}"


def cloudevent_headers(event_id: str) -> Headers:
    return [
        ("ce_specversion", b"1.0"),
        ("ce_id", event_id.encode()),
        ("ce_source", b"/lab"),
        ("ce_type", b"orders.created"),
        ("content-type", b"application/json"),
    ]


def produce(store: Store, send: Sender, clock: Callable[[], int], variant: str, events: list[dict[str, Any]]) -> list[int]:
    produced: list[int] = []
    for event in events:
        event_id = str(event["id"])
        at = clock()
        store.mark_produced(variant, event_id, at)
        send(topic_for(variant), event_id.encode(), json.dumps(event).encode(), cloudevent_headers(event_id))
        produced.append(at)
    return produced
