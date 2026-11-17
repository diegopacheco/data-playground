import json
import time
from kafka import KafkaConsumer, KafkaProducer, TopicPartition
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError
from pipeline import BOOTSTRAP

TOPICS = ["orders", "payments", "region_revenue"]


def recreate_topics():
    admin = KafkaAdminClient(bootstrap_servers=BOOTSTRAP)
    try:
        existing = [t for t in admin.list_topics() if t in TOPICS]
        if existing:
            admin.delete_topics(existing)
        deadline = time.time() + 30
        while True:
            try:
                admin.create_topics([NewTopic(t, 1, 1) for t in TOPICS])
                return
            except TopicAlreadyExistsError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
    finally:
        admin.close()


class Producer:
    def __init__(self):
        self.producer = KafkaProducer(
            bootstrap_servers=BOOTSTRAP,
            key_serializer=lambda k: str(k).encode(),
            value_serializer=lambda v: json.dumps(v).encode(),
            linger_ms=5,
        )

    def send(self, topic, key, value):
        self.producer.send(topic, key=key, value=value)

    def close(self):
        self.producer.flush()
        self.producer.close()


def read_topic(topic):
    consumer = KafkaConsumer(bootstrap_servers=BOOTSTRAP, enable_auto_commit=False)
    try:
        partition = TopicPartition(topic, 0)
        consumer.assign([partition])
        consumer.seek_to_beginning(partition)
        end = consumer.end_offsets([partition])[partition]
        records = []
        deadline = time.time() + 20
        while consumer.position(partition) < end and time.time() < deadline:
            for batch in consumer.poll(timeout_ms=500).values():
                for r in batch:
                    records.append({
                        "offset": r.offset,
                        "key": json.loads(r.key) if r.key else None,
                        "value": json.loads(r.value) if r.value else None,
                    })
        return records
    finally:
        consumer.close()


def compact(records):
    latest = {}
    for r in records:
        key = json.dumps(r["key"], sort_keys=True)
        if r["value"] is None:
            latest.pop(key, None)
        else:
            latest[key] = r["value"]
    return list(latest.values())
