import threading
import time

from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer, TopicPartition

from streambench.config import BenchConfig
from streambench.pacer import due
from streambench.payload import encode, now_us
from streambench.recorder import Recorder
from streambench.result import ProducerOutcome

TOPIC_CONFIGS = {"message.timestamp.type": "LogAppendTime", "min.insync.replicas": "1"}


def create_topic(cfg: BenchConfig) -> None:
    admin = KafkaAdminClient(bootstrap_servers=cfg.address)
    admin.create_topics(
        {cfg.topic: {"num_partitions": cfg.partitions, "replication_factor": 1, "configs": TOPIC_CONFIGS}},
        wait_for_metadata=True,
    )
    admin.close()


class ErrorCounter:
    def __init__(self) -> None:
        self.count = 0
        self.lock = threading.Lock()

    def __call__(self, _error: BaseException) -> None:
        with self.lock:
            self.count += 1


def produce(cfg: BenchConfig) -> ProducerOutcome:
    producer = KafkaProducer(bootstrap_servers=cfg.address, acks="all", linger_ms=0, enable_idempotence=True)
    errors = ErrorCounter()
    started_at_us = now_us()
    begin = time.perf_counter()
    sent = 0
    while (elapsed := time.perf_counter() - begin) < cfg.seconds:
        count = due(elapsed, cfg.rate, sent, cfg.batch_cap)
        if count == 0:
            time.sleep(0.0002)
            continue
        for seq in range(sent, sent + count):
            future = producer.send(cfg.topic, value=encode(seq, now_us(), cfg.size), partition=seq % cfg.partitions)
            future.add_errback(errors)
        sent += count
    producer.flush()
    finished_at_us = now_us()
    producer.close()
    return ProducerOutcome(sent, errors.count, started_at_us, finished_at_us)


def consume(cfg: BenchConfig, recorder: Recorder, ready: threading.Event, stop: threading.Event) -> None:
    consumer = KafkaConsumer(
        bootstrap_servers=cfg.address,
        enable_auto_commit=False,
        fetch_max_wait_ms=100,
        fetch_min_bytes=1,
        max_partition_fetch_bytes=4 * 1024 * 1024,
    )
    partitions = [TopicPartition(cfg.topic, p) for p in range(cfg.partitions)]
    consumer.assign(partitions)
    consumer.seek_to_beginning(*partitions)
    consumer.poll(timeout_ms=0)
    ready.set()
    while not stop.is_set():
        batches = consumer.poll(timeout_ms=100)
        received_at_us = now_us()
        for tp, records in batches.items():
            for record in records:
                recorder.observe(tp.partition, record.value, record.timestamp * 1000, received_at_us)
    consumer.close()


def drain(recorder: Recorder, sent: int, seconds: float) -> None:
    deadline = time.perf_counter() + seconds
    while recorder.received < sent and time.perf_counter() < deadline:
        time.sleep(0.01)


def run(cfg: BenchConfig) -> tuple[ProducerOutcome, Recorder]:
    create_topic(cfg)
    ready = threading.Event()
    stop = threading.Event()
    recorder = Recorder(cfg.partitions, 0, 1000)
    thread = threading.Thread(target=consume, args=(cfg, recorder, ready, stop))
    thread.start()
    if not ready.wait(30):
        raise TimeoutError("kafka consumer did not get ready in 30s")
    recorder.warmup_until_us = now_us() + int(cfg.warmup_seconds * 1_000_000)
    producer = produce(cfg)
    drain(recorder, producer.sent, cfg.drain_seconds)
    stop.set()
    thread.join()
    return producer, recorder
