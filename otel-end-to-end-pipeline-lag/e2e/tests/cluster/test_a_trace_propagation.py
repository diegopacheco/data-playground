import time

from harness import jaeger, pipeline

PRODUCER = "order-producer"
CONSUMER = "lag-consumer"


def test_one_trace_spans_producer_kafka_consumer_and_sink_for_a_given_message_id() -> None:
    run_id = f"trace-{int(time.time())}"
    acked = pipeline.produce(run_id, rate=20, seconds=3)
    rows = pipeline.wait_for_sink(run_id, acked)
    assert len(rows) == acked > 0
    assert len({r.trace_id for r in rows}) == len(rows), "every message must get its own trace"

    message = rows[len(rows) // 2]
    spans = jaeger.wait_for_trace(message.trace_id, {PRODUCER, CONSUMER}, min_spans=3)
    by_id = {s.span_id: s for s in spans}
    services = {s.service for s in spans}
    assert {PRODUCER, CONSUMER} <= services, services

    send = next(s for s in spans if s.service == PRODUCER and s.kind == "producer")
    process = next(s for s in spans if s.service == CONSUMER and s.kind == "consumer")
    sink = next(s for s in spans if s.service == CONSUMER and s.kind == "client")

    assert process.parent_id == send.span_id, "consumer span must be a child of the producer span from the Kafka header"
    assert sink.parent_id == process.span_id
    assert process.tags["order.id"] == message.id
    assert by_id[process.parent_id].service == PRODUCER

    print(f"\nRESULT trace message={message.id} trace_id={message.trace_id} spans={len(spans)}")
    for s in spans:
        print(f"  {s.service:15} {s.kind:9} {s.name:24} span={s.span_id} parent={s.parent_id}")
