import os
import time
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import UnknownTopicOrPartitionError
from data import encode

BROKER = os.environ.get("KAFKA_BROKER", "localhost:31104")
GAP = 0.01


def recreate_topics(prefixes, new):
    admin = KafkaAdminClient(bootstrap_servers=BROKER, request_timeout_ms=30000)
    try:
        stale = [t for t in admin.list_topics() if t.startswith(tuple(prefixes))]
        if stale:
            try:
                admin.delete_topics(stale)
            except UnknownTopicOrPartitionError:
                pass
        admin.create_topics([NewTopic(t, num_partitions=1, replication_factor=1) for t in new])
    finally:
        admin.close()


class Producer:
    def __init__(self, topics):
        self.topics = topics
        self.p = KafkaProducer(bootstrap_servers=BROKER, acks="all", linger_ms=0, max_in_flight_requests_per_connection=1)
        self.offsets = {t: 0 for t in topics.values()}

    def send(self, events):
        started = time.time()
        for e in events:
            topic = self.topics[e["topic"]]
            self.p.send(topic, key=e["key"].encode(), value=encode(e["value"])).get(timeout=30)
            self.offsets[topic] += 1
            time.sleep(GAP)
        return round((time.time() - started) * 1000)

    def close(self):
        self.p.close()
