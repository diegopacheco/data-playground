import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class JobArgs:
    bootstrap: str
    topic: str
    table: str
    checkpoint: str
    trigger_seconds: int
    starting_offsets: str


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("trigger-seconds must be at least 1")
    return number


def parse(argv: list[str]) -> JobArgs:
    parser = argparse.ArgumentParser(prog="events-python")
    parser.add_argument("--bootstrap", default="kafka-0.kafka:9092")
    parser.add_argument("--topic", default="events")
    parser.add_argument("--table", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--trigger-seconds", type=positive, default=5)
    parser.add_argument("--starting-offsets", default="latest")
    ns = parser.parse_args(argv)
    return JobArgs(ns.bootstrap, ns.topic, ns.table, ns.checkpoint, ns.trigger_seconds, ns.starting_offsets)
