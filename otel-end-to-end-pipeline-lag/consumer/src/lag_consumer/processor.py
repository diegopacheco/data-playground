import time
from collections.abc import Callable

from opentelemetry.trace import SpanKind

from lag_consumer.order import enrich, lag_seconds, parse
from lag_consumer.sink import Sink
from lag_consumer.telemetry import Headers, Telemetry, parent_context


def handle(
    value: bytes,
    headers: Headers,
    topic: str,
    sink: Sink,
    telemetry: Telemetry,
    now: Callable[[], float] = time.time,
) -> float | None:
    with telemetry.tracer.start_as_current_span(
        f"{topic} process",
        context=parent_context(headers),
        kind=SpanKind.CONSUMER,
        attributes={"messaging.system": "kafka", "messaging.destination.name": topic},
    ) as span:
        order = parse(value)
        if order is None:
            span.set_attribute("order.invalid", True)
            return None
        span.set_attribute("order.id", order.id)
        enriched = enrich(order)
        span.set_attribute("order.tier", enriched.tier)
        trace_id = format(span.get_span_context().trace_id, "032x")
        with telemetry.tracer.start_as_current_span(
            "INSERT sink_orders", kind=SpanKind.CLIENT, attributes={"db.system.name": "postgresql"}
        ):
            inserted = sink.write(enriched, trace_id)
        if not inserted:
            span.set_attribute("order.duplicate", True)
            return None
        lag = lag_seconds(order.event_time_ms, now())
        telemetry.lag.record(lag)
        span.set_attribute("pipeline.e2e_lag_seconds", lag)
        return lag
