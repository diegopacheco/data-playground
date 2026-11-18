import os
import time
import uuid

from kafka import KafkaProducer

from eventgen.events import due, event


def run(bootstrap: str, topic: str, rate: int, source: str) -> None:
    producer = KafkaProducer(bootstrap_servers=bootstrap, acks="all", enable_idempotence=True, linger_ms=0)
    start = time.monotonic()
    seq = 0
    print(f"producing to {topic} at {rate}/s as {source}", flush=True)
    while True:
        wait = due(start, seq, rate) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        producer.send(topic, event(source, seq, time.time_ns() // 1_000_000).encode())
        seq += 1
        if seq % (rate * 10) == 0:
            print(f"sent {seq}", flush=True)


if __name__ == "__main__":
    run(
        os.environ.get("BOOTSTRAP", "kafka-0.kafka:9092"),
        os.environ.get("TOPIC", "events"),
        int(os.environ.get("RATE", "50")),
        f"{os.environ.get('HOSTNAME', 'producer')}-{uuid.uuid4().hex[:8]}",
    )
