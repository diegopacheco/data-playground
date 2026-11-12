import asyncio
import json
from typing import Any

from lab.app import Message, build
from lab.events import Headers, cloudevent_headers, produce, topic_for
from lab.store import Store


class Clock:
    def __init__(self) -> None:
        self.now = 1000

    def __call__(self) -> int:
        self.now += 5
        return self.now


def test_each_variant_has_its_own_topic_so_cold_starts_do_not_wake_each_other() -> None:
    assert {topic_for(v) for v in ("native", "jvm", "jvm-aot", "python")} == {
        "orders-native", "orders-jvm", "orders-jvm-aot", "orders-python",
    }


def test_records_carry_cloudevent_binary_headers_so_the_source_sends_json_with_the_order_id() -> None:
    headers = dict(cloudevent_headers("o-1"))
    assert headers["ce_id"] == b"o-1"
    assert headers["content-type"] == b"application/json"
    assert headers["ce_specversion"] == b"1.0"


def test_produced_time_is_taken_before_the_send_so_latency_includes_the_broker_hop() -> None:
    store, clock = Store(), Clock()
    order: list[str] = []

    def send(topic: str, key: bytes, value: bytes, headers: Headers) -> None:
        order.append(f"send {key.decode()} at {clock.now}")

    produced = produce(store, send, clock, "native", [{"id": "a"}, {"id": "b"}])
    assert produced == [1005, 1010]
    assert order == ["send a at 1005", "send b at 1010"]
    store.add({"variant": "native", "id": "a"}, 2000)
    assert store.records_for("native")[0]["producedAtMs"] == 1005


def test_duplicate_deliveries_stay_visible_so_tests_can_catch_them() -> None:
    store = Store()
    store.add({"variant": "jvm", "id": "a"}, 1)
    store.add({"variant": "jvm", "id": "a"}, 2)
    assert [r["receivedAtMs"] for r in store.records_for("jvm")] == [1, 2]


def test_reset_only_clears_one_variant() -> None:
    store = Store()
    store.mark_produced("jvm", "a", 1)
    store.add({"variant": "jvm", "id": "a"}, 2)
    store.add({"variant": "python", "id": "b"}, 3)
    store.reset("jvm")
    assert store.records_for("jvm") == []
    assert len(store.records_for("python")) == 1


def call(app: Any, method: str, path: str, query: bytes = b"", body: bytes = b"") -> tuple[int, bytes]:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    asyncio.run(app({"type": "http", "method": method, "path": path, "query_string": query}, receive, send))
    return sent[0]["status"], sent[1]["body"]


def test_http_round_trip_from_produce_to_records() -> None:
    store, clock = Store(), Clock()
    topics: list[str] = []
    app = build(store, lambda t, k, v, h: topics.append(t), clock)
    payload = json.dumps({"variant": "python", "events": [{"id": "x"}]}).encode()
    assert call(app, "POST", "/produce", body=payload)[0] == 200
    assert topics == ["orders-python"]
    record = json.dumps({"variant": "python", "id": "x", "handledAtMs": 1}).encode()
    assert call(app, "POST", "/records", body=record)[0] == 204
    status, body = call(app, "GET", "/records", query=b"variant=python")
    assert status == 200
    assert [(r["id"], r["producedAtMs"]) for r in json.loads(body)] == [("x", 1005)]
