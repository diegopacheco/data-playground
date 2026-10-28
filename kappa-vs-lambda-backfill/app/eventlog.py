import json
import os
import time

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

BROKERS = os.environ.get("BROKERS", "r13-redpanda:9092")
TOPIC = os.environ.get("TOPIC", "orders")
CLIENTS = {}


def consumer():
    return Consumer({
        "bootstrap.servers": BROKERS,
        "group.id": "r13-backfill-reader",
        "enable.auto.commit": False,
        "auto.offset.reset": "earliest",
    })


def producer():
    if "producer" not in CLIENTS:
        CLIENTS["producer"] = Producer({"bootstrap.servers": BROKERS, "enable.idempotence": True, "acks": "all", "linger.ms": 5})
    return CLIENTS["producer"]


def probe():
    if "probe" not in CLIENTS:
        CLIENTS["probe"] = consumer()
    return CLIENTS["probe"]


def drop_clients():
    for name in list(CLIENTS):
        client = CLIENTS.pop(name)
        if name == "probe":
            client.close()
        else:
            client.flush(10)


def recreate_topic():
    drop_clients()
    admin = AdminClient({"bootstrap.servers": BROKERS})
    if TOPIC in admin.list_topics(timeout=10).topics:
        admin.delete_topics([TOPIC], operation_timeout=30)[TOPIC].result()
    for _ in range(60):
        try:
            topic = NewTopic(TOPIC, num_partitions=1, replication_factor=1, config={"retention.ms": "-1", "retention.bytes": "-1"})
            admin.create_topics([topic])[TOPIC].result()
            break
        except KafkaException as e:
            if e.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise
            time.sleep(0.5)
    else:
        raise RuntimeError(f"topic {TOPIC} could not be recreated")
    for _ in range(60):
        try:
            if end_offset() == 0:
                return
        except KafkaException:
            drop_clients()
        time.sleep(0.5)
    raise RuntimeError(f"topic {TOPIC} is not readable")


def produce(events):
    p = producer()
    for e in events:
        p.produce(TOPIC, key=e["event_id"], value=json.dumps(e))
        p.poll(0)
    if p.flush(30) != 0:
        raise RuntimeError("producer did not flush every event")
    return len(events)


def end_offset():
    return probe().get_watermark_offsets(TopicPartition(TOPIC, 0), timeout=10)[1]


def read(start, end):
    if start >= end:
        return []
    c = consumer()
    try:
        c.assign([TopicPartition(TOPIC, 0, start)])
        out = []
        last = start - 1
        deadline = time.monotonic() + 10
        while last < end - 1:
            msgs = c.consume(min(2000, end - 1 - last), timeout=0.2)
            if not msgs:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"log read stalled at offset {last + 1}")
                continue
            deadline = time.monotonic() + 10
            for m in msgs:
                if m.error():
                    raise RuntimeError(m.error().str())
                last = m.offset()
                if last < end:
                    out.append((last, json.loads(m.value())))
        return out
    finally:
        c.close()
