import os
import time

from kafka import KafkaProducer

from lab.app import build
from lab.events import Headers
from lab.store import Store

producer = KafkaProducer(
    bootstrap_servers=os.environ.get("BOOTSTRAP", "localhost:9092"),
    acks="all",
    linger_ms=0,
)


def send(topic: str, key: bytes, value: bytes, headers: Headers) -> None:
    producer.send(topic, key=key, value=value, headers=headers).get(timeout=10)


def clock() -> int:
    return time.time_ns() // 1_000_000


app = build(Store(), send, clock)
