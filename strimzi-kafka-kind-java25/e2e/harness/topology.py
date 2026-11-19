import re
from collections import Counter
from dataclasses import dataclass

LINE = re.compile(
    r"Topic:\s*(?P<topic>\S+)\s+Partition:\s*(?P<partition>\d+)\s+Leader:\s*(?P<leader>-?\d+)"
    r"\s+Replicas:\s*(?P<replicas>[\d,]+)\s+Isr:\s*(?P<isr>[\d,]*)"
)


@dataclass(frozen=True)
class Partition:
    topic: str
    partition: int
    leader: int
    replicas: tuple[int, ...]
    isr: tuple[int, ...]


def ids(text: str) -> tuple[int, ...]:
    return tuple(int(x) for x in text.split(",") if x)


def parse_describe(output: str) -> list[Partition]:
    partitions = [
        Partition(m["topic"], int(m["partition"]), int(m["leader"]), ids(m["replicas"]), ids(m["isr"]))
        for m in (LINE.search(line) for line in output.splitlines())
        if m
    ]
    return sorted(partitions, key=lambda p: p.partition)


def replicas_per_broker(partitions: list[Partition]) -> dict[int, int]:
    return dict(sorted(Counter(b for p in partitions for b in p.replicas).items()))


def leaders_per_broker(partitions: list[Partition]) -> dict[int, int]:
    return dict(sorted(Counter(p.leader for p in partitions).items()))


def fully_in_sync(partitions: list[Partition]) -> bool:
    return all(set(p.isr) == set(p.replicas) and p.leader in p.replicas for p in partitions)


def render(partitions: list[Partition]) -> str:
    rows = [f"  p{p.partition:<3} leader={p.leader} replicas={','.join(map(str, p.replicas))}" for p in partitions]
    summary = f"  replicas per broker {replicas_per_broker(partitions)} leaders per broker {leaders_per_broker(partitions)}"
    return "\n".join([*rows, summary])
