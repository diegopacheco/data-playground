import asyncio
import time
from datetime import timedelta

from apache_iggy import (
    Consumer,
    Durability,
    IggyClient,
    PollingStrategy,
    PollOptions,
    SendMessage,
    TopicOptions,
)

from streambench.config import STREAM, BenchConfig
from streambench.pacer import due
from streambench.payload import encode, now_us
from streambench.recorder import Recorder
from streambench.result import ProducerOutcome

USERNAME = "iggy"
PASSWORD = "iggy"
POLL = PollOptions(count=1000, max_wait=timedelta(milliseconds=100), max_bytes=4 * 1024 * 1024)


async def connect(address: str) -> IggyClient:
    client = IggyClient(address)
    await client.connect()
    await client.login_user(USERNAME, PASSWORD)
    return client


async def create_topic(client: IggyClient, cfg: BenchConfig) -> None:
    if await client.get_stream(STREAM) is None:
        await client.create_stream(STREAM)
    options = TopicOptions(partitions_count=cfg.partitions, durability=Durability.REPLICATED)
    await client.create_topic(STREAM, cfg.topic, options)


async def produce(client: IggyClient, cfg: BenchConfig) -> ProducerOutcome:
    started_at_us = now_us()
    begin = time.perf_counter()
    sent = 0
    while (elapsed := time.perf_counter() - begin) < cfg.seconds:
        count = due(elapsed, cfg.rate, sent, cfg.batch_cap)
        if count == 0:
            await asyncio.sleep(0.0002)
            continue
        groups: dict[int, list[SendMessage]] = {}
        for seq in range(sent, sent + count):
            groups.setdefault(seq % cfg.partitions, []).append(SendMessage(encode(seq, now_us(), cfg.size)))
        for partition, messages in groups.items():
            await client.send_messages(STREAM, cfg.topic, partition, messages)
        sent += count
    return ProducerOutcome(sent, 0, started_at_us, now_us())


async def consume(client: IggyClient, cfg: BenchConfig, partition: int, recorder: Recorder, stop: asyncio.Event) -> None:
    strategy = PollingStrategy.Offset(0)
    while not stop.is_set():
        polled = await client.poll_messages(
            STREAM, cfg.topic, partition_id=partition, consumer=Consumer.Single(1), polling_strategy=strategy, options=POLL
        )
        received_at_us = now_us()
        for message in polled.messages:
            recorder.observe(partition, message.payload(), message.timestamp(), received_at_us)
        if polled.messages:
            strategy = polled.continuation()


async def drain(recorder: Recorder, sent: int, seconds: float) -> None:
    deadline = time.perf_counter() + seconds
    while recorder.received < sent and time.perf_counter() < deadline:
        await asyncio.sleep(0.01)


async def run_async(cfg: BenchConfig) -> tuple[ProducerOutcome, Recorder]:
    admin = await connect(cfg.address)
    await create_topic(admin, cfg)
    consumers = [await connect(cfg.address) for _ in range(cfg.partitions)]
    recorder = Recorder(cfg.partitions, now_us() + int(cfg.warmup_seconds * 1_000_000), 1)
    stop = asyncio.Event()
    tasks = [asyncio.create_task(consume(c, cfg, p, recorder, stop)) for p, c in enumerate(consumers)]
    producer = await produce(admin, cfg)
    await drain(recorder, producer.sent, cfg.drain_seconds)
    stop.set()
    await asyncio.gather(*tasks)
    for client in [admin, *consumers]:
        await client.disconnect()
    return producer, recorder


def run(cfg: BenchConfig) -> tuple[ProducerOutcome, Recorder]:
    return asyncio.run(run_async(cfg))
