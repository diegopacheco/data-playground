from typing import Protocol

from pg8000.native import Connection

from lag_consumer.config import Settings
from lag_consumer.order import EnrichedOrder

SCHEMA = """
CREATE TABLE IF NOT EXISTS sink_orders (
    id text PRIMARY KEY,
    run_id text NOT NULL,
    seq bigint NOT NULL,
    sku text NOT NULL,
    qty int NOT NULL,
    price_cents bigint NOT NULL,
    total_cents bigint NOT NULL,
    tier text NOT NULL,
    event_time timestamptz NOT NULL,
    sink_time timestamptz NOT NULL DEFAULT clock_timestamp(),
    trace_id text NOT NULL
)
"""

INSERT = """
INSERT INTO sink_orders (id, run_id, seq, sku, qty, price_cents, total_cents, tier, event_time, trace_id)
VALUES (:id, :run_id, :seq, :sku, :qty, :price_cents, :total_cents, :tier, to_timestamp(:event_time_ms / 1000.0), :trace_id)
ON CONFLICT (id) DO NOTHING
RETURNING id
"""


class Sink(Protocol):
    def write(self, enriched: EnrichedOrder, trace_id: str) -> bool: ...


class PostgresSink:
    def __init__(self, settings: Settings) -> None:
        self.connection = Connection(
            user=settings.pg_user,
            password=settings.pg_password,
            host=settings.pg_host,
            database=settings.pg_database,
        )
        self.connection.run(SCHEMA)

    def write(self, enriched: EnrichedOrder, trace_id: str) -> bool:
        order = enriched.order
        rows = self.connection.run(
            INSERT,
            id=order.id,
            run_id=order.run_id,
            seq=order.seq,
            sku=order.sku,
            qty=order.qty,
            price_cents=order.price_cents,
            total_cents=enriched.total_cents,
            tier=enriched.tier,
            event_time_ms=order.event_time_ms,
            trace_id=trace_id,
        )
        return bool(rows)
