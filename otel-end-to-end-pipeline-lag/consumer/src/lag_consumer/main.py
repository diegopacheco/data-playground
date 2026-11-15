import json
import signal
import sys
import time
from types import FrameType

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from lag_consumer import telemetry
from lag_consumer.config import Settings, load
from lag_consumer.processor import handle
from lag_consumer.sink import PostgresSink, Sink


def emit(event: object) -> None:
    print(json.dumps(event), flush=True)


def stop(signum: int, frame: FrameType | None) -> None:
    sys.exit(0)


def connect(settings: Settings) -> KafkaConsumer:
    return KafkaConsumer(
        settings.topic,
        bootstrap_servers=settings.bootstrap,
        group_id=settings.group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )


def consume(consumer: KafkaConsumer, settings: Settings, sink: Sink, tel: telemetry.Telemetry) -> None:
    while True:
        batch = consumer.poll(timeout_ms=200)
        if not batch:
            continue
        if settings.slowdown_ms:
            time.sleep(settings.slowdown_ms / 1000)
        for records in batch.values():
            for record in records:
                handle(record.value, record.headers or [], record.topic, sink, tel)
        try:
            consumer.commit()
        except KafkaError as error:
            emit({"commit_failed": repr(error)})


def run() -> None:
    signal.signal(signal.SIGTERM, stop)
    settings = load()
    tel = telemetry.otlp()
    emit({"started": settings.topic, "group": settings.group, "slowdown_ms": settings.slowdown_ms})
    consumer = connect(settings)
    try:
        consume(consumer, settings, PostgresSink(settings), tel)
    finally:
        consumer.close()
        tel.shutdown()


if __name__ == "__main__":
    run()
