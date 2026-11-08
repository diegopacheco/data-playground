from collections.abc import Mapping
from dataclasses import dataclass

STREAM = "bench"


@dataclass(frozen=True)
class BenchConfig:
    broker: str
    address: str
    topic: str
    rate: int
    size: int
    seconds: float
    warmup_seconds: float
    partitions: int
    batch_cap: int
    drain_seconds: float

    @staticmethod
    def from_env(env: Mapping[str, str]) -> "BenchConfig":
        broker = env["BROKER"]
        if broker not in ("iggy", "kafka"):
            raise ValueError(f"BROKER must be iggy or kafka, got {broker}")
        return BenchConfig(
            broker=broker,
            address=env["IGGY_ADDRESS"] if broker == "iggy" else env["KAFKA_BOOTSTRAP"],
            topic=env["TOPIC"],
            rate=int(env.get("RATE", "1000")),
            size=int(env.get("SIZE", "100")),
            seconds=float(env.get("SECONDS", "10")),
            warmup_seconds=float(env.get("WARMUP_SECONDS", "2")),
            partitions=int(env.get("PARTITIONS", "3")),
            batch_cap=int(env.get("BATCH_CAP", "1000")),
            drain_seconds=float(env.get("DRAIN_SECONDS", "15")),
        )
