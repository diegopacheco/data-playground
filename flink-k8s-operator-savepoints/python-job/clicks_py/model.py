import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class JobArgs:
    version: str
    users: int
    rate: int


def user_for(seq: int, users: int) -> str:
    if users < 1:
        raise ValueError("users must be at least 1")
    return f"user-{seq % users}"


def next_count(previous: int | None) -> int:
    return 1 if previous is None else previous + 1


def line(job: str, version: str, user: str, seq: int, count: int) -> str:
    return f"CLICKS job={job} version={version} user={user} seq={seq} count={count}"


def parse_args(argv: list[str]) -> JobArgs:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--rate", type=int, default=20)
    known, _ = parser.parse_known_args(argv)
    return JobArgs(known.version, known.users, known.rate)
