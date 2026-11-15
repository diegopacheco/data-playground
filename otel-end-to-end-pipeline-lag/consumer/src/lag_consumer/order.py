import json
from dataclasses import dataclass

BIG_ORDER_CENTS = 20_000


@dataclass(frozen=True)
class Order:
    id: str
    run_id: str
    seq: int
    sku: str
    qty: int
    price_cents: int
    event_time_ms: int


@dataclass(frozen=True)
class EnrichedOrder:
    order: Order
    total_cents: int
    tier: str


def parse(raw: bytes) -> Order | None:
    try:
        data = json.loads(raw)
        return Order(
            id=str(data["id"]),
            run_id=str(data["runId"]),
            seq=int(data["seq"]),
            sku=str(data["sku"]),
            qty=int(data["qty"]),
            price_cents=int(data["priceCents"]),
            event_time_ms=int(data["eventTimeMs"]),
        )
    except (ValueError, KeyError, TypeError):
        return None


def enrich(order: Order) -> EnrichedOrder:
    total = order.qty * order.price_cents
    return EnrichedOrder(order=order, total_cents=total, tier="big" if total >= BIG_ORDER_CENTS else "small")


def lag_seconds(event_time_ms: int, sink_time_s: float) -> float:
    return max(0.0, sink_time_s - event_time_ms / 1000)
