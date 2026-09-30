import hashlib
import json
import os
import time
import uuid
from confluent_kafka import Consumer, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

BOOTSTRAP = os.environ.get("BOOTSTRAP", "r9-controller:9092,r9-broker:9092")
PARTITIONS = int(os.environ.get("PARTITIONS", "6"))


def admin():
    return AdminClient({"bootstrap.servers": BOOTSTRAP})


def fingerprint(values):
    digest = hashlib.sha256()
    for value in sorted(values):
        digest.update(value)
        digest.update(b"\n")
    return digest.hexdigest()


def recreate_topic(topic):
    client = admin()
    if topic in client.list_topics(timeout=10).topics:
        client.delete_topics([topic])[topic].result(30)
        deadline = time.time() + 30
        while topic in client.list_topics(timeout=10).topics and time.time() < deadline:
            time.sleep(0.5)
    deadline = time.time() + 30
    while True:
        try:
            client.create_topics([NewTopic(topic, PARTITIONS, 1)])[topic].result(30)
            break
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(1)
    while len(client.list_topics(topic, timeout=10).topics[topic].partitions) < PARTITIONS:
        time.sleep(0.5)


def produce(topic, lines):
    producer = Producer({"bootstrap.servers": BOOTSTRAP, "acks": "all", "enable.idempotence": True, "linger.ms": 20})
    failures = []
    for line in lines:
        key = json.loads(line)["order_id"]
        producer.produce(topic, key=key, value=line, on_delivery=lambda err, msg: err and failures.append(str(err)))
        producer.poll(0)
    remaining = producer.flush(60)
    if remaining or failures:
        raise RuntimeError(f"{remaining} undelivered, {len(failures)} failed: {failures[:3]}")
    return {"records": len(lines), "bytes": sum(len(line) for line in lines), "sha256": fingerprint(lines)}


def end_offsets(topic):
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"r9-offsets-{uuid.uuid4()}"})
    try:
        partitions = consumer.list_topics(topic, timeout=10).topics[topic].partitions
        return {p: consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=10)[1] for p in partitions}
    finally:
        consumer.close()


def consume(topic, timeout=90):
    wanted = end_offsets(topic)
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"r9-verify-{uuid.uuid4()}", "auto.offset.reset": "earliest", "enable.auto.commit": False})
    consumer.subscribe([topic])
    values, positions, per_partition = [], {}, {}
    deadline = time.time() + timeout
    started = time.time()
    try:
        while any(positions.get(p, 0) < end for p, end in wanted.items()):
            if time.time() > deadline:
                raise TimeoutError(f"read {len(values)} records, wanted {sum(wanted.values())}")
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise RuntimeError(str(msg.error()))
            values.append(msg.value())
            positions[msg.partition()] = msg.offset() + 1
            per_partition[msg.partition()] = per_partition.get(msg.partition(), 0) + 1
    finally:
        consumer.close()
    return {"records": len(values), "bytes": sum(len(v) for v in values), "sha256": fingerprint(values), "per_partition": {str(k): v for k, v in sorted(per_partition.items())}, "seconds": round(time.time() - started, 2), "values": values}


def cluster():
    metadata = admin().list_topics(timeout=10)
    brokers = [{"id": b.id, "host": b.host, "port": b.port} for b in sorted(metadata.brokers.values(), key=lambda b: b.id)]
    topics = []
    for name, topic in sorted(metadata.topics.items()):
        if name.startswith("__"):
            continue
        partitions = [{"partition": p.id, "leader": p.leader, "replicas": list(p.replicas), "isr": list(p.isrs)} for p in sorted(topic.partitions.values(), key=lambda p: p.id)]
        topics.append({"name": name, "partitions": partitions})
    return {"cluster_id": metadata.cluster_id, "controller": metadata.controller_id, "brokers": brokers, "topics": topics}
