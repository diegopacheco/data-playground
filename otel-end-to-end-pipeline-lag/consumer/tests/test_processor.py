from opentelemetry.sdk.metrics.export import HistogramDataPoint, InMemoryMetricReader
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind

from lag_consumer.order import EnrichedOrder
from lag_consumer.processor import handle
from lag_consumer.telemetry import LAG_BUCKETS, LAG_METRIC, Telemetry, build

PRODUCER_TRACE = "4bf92f3577b34da6a3ce929d0e0e4736"
PRODUCER_SPAN = "00f067aa0ba902b7"
HEADERS = [("traceparent", f"00-{PRODUCER_TRACE}-{PRODUCER_SPAN}-01".encode())]
EVENT_MS = 1_700_000_000_000


def raw(order_id: str) -> bytes:
    return (
        f'{{"id":"{order_id}","runId":"r","seq":1,"sku":"s","qty":1,"priceCents":100,"eventTimeMs":{EVENT_MS}}}'
    ).encode()


class MemorySink:
    def __init__(self) -> None:
        self.rows: dict[str, str] = {}

    def write(self, enriched: EnrichedOrder, trace_id: str) -> bool:
        if enriched.order.id in self.rows:
            return False
        self.rows[enriched.order.id] = trace_id
        return True


def setup() -> tuple[Telemetry, InMemorySpanExporter, InMemoryMetricReader]:
    spans = InMemorySpanExporter()
    metrics = InMemoryMetricReader()
    return build(SimpleSpanProcessor(spans), metrics), spans, metrics


def lag_point(reader: InMemoryMetricReader) -> HistogramDataPoint:
    data = reader.get_metrics_data()
    assert data is not None
    for resource in data.resource_metrics:
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                if metric.name == LAG_METRIC:
                    point = metric.data.data_points[0]
                    assert isinstance(point, HistogramDataPoint)
                    return point
    raise AssertionError("lag histogram not exported")


def test_consumer_span_continues_the_producer_trace_from_the_kafka_headers() -> None:
    tel, spans, _ = setup()
    sink = MemorySink()
    handle(raw("r-1"), HEADERS, "orders", sink, tel, now=lambda: EVENT_MS / 1000 + 0.3)
    finished = {s.name: s for s in spans.get_finished_spans()}
    process = finished["orders process"]
    insert = finished["INSERT sink_orders"]
    assert process.kind == SpanKind.CONSUMER
    assert format(process.context.trace_id, "032x") == PRODUCER_TRACE
    assert process.parent is not None and format(process.parent.span_id, "016x") == PRODUCER_SPAN
    assert insert.parent is not None and insert.parent.span_id == process.context.span_id
    assert sink.rows["r-1"] == PRODUCER_TRACE


def test_lag_lands_in_the_bucket_the_slo_counts_as_good() -> None:
    tel, _, metrics = setup()
    sink = MemorySink()
    handle(raw("fast"), HEADERS, "orders", sink, tel, now=lambda: EVENT_MS / 1000 + 1.9)
    handle(raw("slow"), HEADERS, "orders", sink, tel, now=lambda: EVENT_MS / 1000 + 2.1)
    point = lag_point(metrics)
    assert 2.0 in LAG_BUCKETS
    within_2s = sum(point.bucket_counts[: LAG_BUCKETS.index(2.0) + 1])
    assert point.count == 2
    assert within_2s == 1


def test_redelivered_message_is_not_counted_twice_so_histogram_count_equals_sink_rows() -> None:
    tel, _, metrics = setup()
    sink = MemorySink()
    first = handle(raw("dup"), HEADERS, "orders", sink, tel, now=lambda: EVENT_MS / 1000 + 0.5)
    second = handle(raw("dup"), HEADERS, "orders", sink, tel, now=lambda: EVENT_MS / 1000 + 9.0)
    assert first == 0.5
    assert second is None
    assert lag_point(metrics).count == len(sink.rows) == 1


def test_message_without_trace_headers_still_gets_its_own_trace() -> None:
    tel, spans, _ = setup()
    sink = MemorySink()
    handle(raw("orphan"), [], "orders", sink, tel, now=lambda: EVENT_MS / 1000)
    process = next(s for s in spans.get_finished_spans() if s.name == "orders process")
    assert process.parent is None
    assert sink.rows["orphan"] == format(process.context.trace_id, "032x")
