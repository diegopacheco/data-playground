import asyncio
import json

import pytest

from orders import probe
from orders.app import Message, Runtime, build
from orders.lab import HandledRecord
from orders.transform import OrderEvent, ProcessedOrder, apply, parse_event

STAT = "42 (java (main) x) S 1 42 42 0 -1 4194560 100 0 0 0 5 3 0 0 20 0 20 0 12345 1000000 2000 0"


def test_total_matches_the_java_transform_so_every_variant_bills_the_same() -> None:
    assert apply(OrderEvent("o-1", " ab-12 ", 3, 1250)) == ProcessedOrder("o-1", "AB-12", 3750)


def test_event_body_uses_the_same_camel_case_contract_as_the_java_service() -> None:
    body = json.dumps({"id": "o-9", "sku": "x-1", "quantity": 2, "unitPriceCents": 99}).encode()
    assert parse_event(body) == OrderEvent("o-9", "x-1", 2, 99)


@pytest.mark.parametrize("event", [OrderEvent("o", "x", 0, 1), OrderEvent("o", "x", 1, -1), OrderEvent(" ", "x", 1, 1)])
def test_invalid_orders_fail_so_the_source_retries_instead_of_recording_garbage(event: OrderEvent) -> None:
    with pytest.raises(ValueError):
        apply(event)


def test_totals_beyond_64_bits_are_rejected_like_java_multiply_exact() -> None:
    with pytest.raises(ValueError):
        apply(OrderEvent("o", "x", 2**31 - 1, 2**62))


def test_process_start_comes_from_uptime_not_whole_second_btime() -> None:
    now = 1_700_000_000_000
    assert probe.started_at_ms(STAT, "130.45 900.00\n", now, 10.0) == now - (130_450 - 123_450)


def test_rss_is_read_from_vm_rss() -> None:
    assert probe.rss_kb("Name:\tpython\nVmRSS:\t   40960 kB\n") == 40960
    assert probe.rss_kb("Name:\tpython\n") == -1


def run_app(body: bytes) -> tuple[list[Message], list[HandledRecord]]:
    runtime = Runtime(variant="python", pod="p-1", started_at_ms=1000)
    reported: list[HandledRecord] = []
    app = build(runtime, reported.append, lambda: (10, 20))
    sent: list[Message] = []
    inbox: list[Message] = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def lifespan_receive() -> Message:
        return inbox.pop(0)

    async def http_receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    async def scenario() -> None:
        await app({"type": "lifespan"}, lifespan_receive, send)
        await app({"type": "http", "method": "POST", "path": "/"}, http_receive, send)

    asyncio.run(scenario())
    return sent, reported


def test_handled_event_is_reported_once_with_startup_timeline() -> None:
    body = json.dumps({"id": "o-7", "sku": "ab", "quantity": 4, "unitPriceCents": 25}).encode()
    sent, reported = run_app(body)
    assert len(reported) == 1
    record = reported[0]
    assert (record.id, record.sku, record.total_cents, record.variant) == ("o-7", "AB", 100, "python")
    assert record.started_at_ms <= record.ready_at_ms <= record.handled_at_ms
    assert (record.rss_kb, record.cgroup_bytes) == (10, 20)
    status = [m["status"] for m in sent if m["type"] == "http.response.start"]
    assert status == [200]


def test_failed_transform_reports_nothing_so_a_retry_does_not_double_count() -> None:
    body = json.dumps({"id": "o-8", "sku": "ab", "quantity": 0, "unitPriceCents": 25}).encode()
    with pytest.raises(ValueError):
        run_app(body)


def test_record_json_matches_the_java_record_field_names() -> None:
    record = HandledRecord("python", "o", "S", 1, "p", 2, 3, 4, 5, 6)
    assert set(json.loads(record.to_json())) == {
        "variant", "id", "sku", "totalCents", "pod", "startedAtMs", "readyAtMs", "handledAtMs", "rssKb", "cgroupBytes",
    }
