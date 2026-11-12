import json
from dataclasses import dataclass

MAX_TOTAL_CENTS = 2**63 - 1


@dataclass(frozen=True)
class OrderEvent:
    id: str
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class ProcessedOrder:
    id: str
    sku: str
    total_cents: int


def parse_event(body: bytes) -> OrderEvent:
    data = json.loads(body)
    return OrderEvent(
        id=str(data["id"]),
        sku=str(data["sku"]),
        quantity=int(data["quantity"]),
        unit_price_cents=int(data["unitPriceCents"]),
    )


def apply(event: OrderEvent) -> ProcessedOrder:
    if not event.id.strip():
        raise ValueError("order id is required")
    if event.quantity <= 0 or event.unit_price_cents < 0:
        raise ValueError(f"order {event.id} has an invalid quantity or price")
    total = event.quantity * event.unit_price_cents
    if total > MAX_TOTAL_CENTS:
        raise ValueError(f"order {event.id} total overflows 64 bits")
    return ProcessedOrder(id=event.id, sku=event.sku.strip().upper(), total_cents=total)
