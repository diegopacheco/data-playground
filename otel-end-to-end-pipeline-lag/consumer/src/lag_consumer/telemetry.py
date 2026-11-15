from collections.abc import Callable, Sequence
from dataclasses import dataclass

from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Histogram
from opentelemetry.propagate import extract
from opentelemetry.propagators.textmap import Getter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanProcessor
from opentelemetry.trace import Tracer

LAG_METRIC = "pipeline.e2e.lag"
LAG_BUCKETS: tuple[float, ...] = (0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 2.5, 5.0, 10.0, 30.0)
SCOPE = "lag-consumer"

Headers = Sequence[tuple[str, bytes]]


class HeaderGetter(Getter[Headers]):
    def get(self, carrier: Headers, key: str) -> list[str] | None:
        values = [value.decode() for name, value in carrier if name.lower() == key.lower() and value is not None]
        return values or None

    def keys(self, carrier: Headers) -> list[str]:
        return [name for name, _ in carrier]


HEADER_GETTER = HeaderGetter()


def parent_context(headers: Headers) -> Context:
    return extract(headers, getter=HEADER_GETTER)


@dataclass(frozen=True)
class Telemetry:
    tracer: Tracer
    lag: Histogram
    shutdown: Callable[[], None]


def build(span_processor: SpanProcessor, metric_reader: MetricReader) -> Telemetry:
    resource = Resource.create()
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(span_processor)
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
        views=[View(instrument_name=LAG_METRIC, aggregation=ExplicitBucketHistogramAggregation(LAG_BUCKETS))],
    )
    lag = meter_provider.get_meter(SCOPE).create_histogram(
        LAG_METRIC, unit="s", description="Event time to sink commit time per message"
    )

    def shutdown() -> None:
        tracer_provider.shutdown()
        meter_provider.shutdown()

    return Telemetry(tracer=tracer_provider.get_tracer(SCOPE), lag=lag, shutdown=shutdown)


def otlp() -> Telemetry:
    return build(
        BatchSpanProcessor(OTLPSpanExporter(), schedule_delay_millis=1000),
        PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=5000),
    )
