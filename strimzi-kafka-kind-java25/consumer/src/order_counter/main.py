import json
import signal
import sys
import time
from types import FrameType

from kafka import KafkaConsumer
from kafka.errors import KafkaError

from order_counter.config import Settings, load
from order_counter.tally import Tally, parse_run_id


def emit(event: object) -> None:
    print(json.dumps(event), flush=True)


def stop(signum: int, frame: FrameType | None) -> None:
    sys.exit(0)


def connect(settings: Settings) -> KafkaConsumer:
    return KafkaConsumer(
        settings.topic,
        bootstrap_servers=settings.bootstrap,
        security_protocol="SASL_PLAINTEXT",
        sasl_mechanism="SCRAM-SHA-512",
        sasl_plain_username=settings.user,
        sasl_plain_password=settings.password,
        group_id=settings.group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )


def consume(consumer: KafkaConsumer, tally: Tally) -> None:
    last_flush = time.monotonic()
    while True:
        batch = consumer.poll(timeout_ms=1000)
        for records in batch.values():
            for record in records:
                run_id = parse_run_id(record.value)
                if run_id is None:
                    emit({"skipped": record.offset, "partition": record.partition})
                    continue
                tally.record(run_id, record.key.decode() if record.key else "")
        if batch:
            try:
                consumer.commit()
            except KafkaError as error:
                emit({"commit_failed": repr(error)})
        if time.monotonic() - last_flush >= 1:
            for summary in tally.drain():
                emit(summary)
            last_flush = time.monotonic()


def run() -> None:
    signal.signal(signal.SIGTERM, stop)
    settings = load()
    emit({"started": settings.topic, "group": settings.group, "user": settings.user})
    consume(connect(settings), Tally())


if __name__ == "__main__":
    run()
