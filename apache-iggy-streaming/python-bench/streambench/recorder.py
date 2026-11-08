from streambench.order import OrderTracker
from streambench.payload import decode


class Recorder:
    def __init__(self, partitions: int, warmup_until_us: int, broker_granularity_us: int) -> None:
        self.tracker = OrderTracker(partitions)
        self.warmup_until_us = warmup_until_us
        self.granularity_us = broker_granularity_us
        self.latencies_us: list[int] = []
        self.ts_checked = 0
        self.ts_violations = 0
        self.min_sent_at_us = 0
        self.max_sent_at_us = 0
        self.last_received_at_us = 0

    @property
    def received(self) -> int:
        return self.tracker.received

    def observe(self, partition: int, data: bytes, broker_ts_us: int, received_at_us: int) -> None:
        stamp = decode(data)
        self.tracker.observe(partition, stamp.seq)
        sent_floor = stamp.sent_at_us // self.granularity_us * self.granularity_us
        self.ts_checked += 1
        if not sent_floor <= broker_ts_us <= received_at_us:
            self.ts_violations += 1
        if self.min_sent_at_us == 0 or stamp.sent_at_us < self.min_sent_at_us:
            self.min_sent_at_us = stamp.sent_at_us
        self.max_sent_at_us = max(self.max_sent_at_us, stamp.sent_at_us)
        self.last_received_at_us = max(self.last_received_at_us, received_at_us)
        if stamp.sent_at_us >= self.warmup_until_us:
            self.latencies_us.append(received_at_us - stamp.sent_at_us)
