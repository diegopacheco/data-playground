import re
from dataclasses import dataclass

LINE = re.compile(r"CLICKS job=(\S+) version=(\S+) user=(\S+) seq=(\d+) count=(\d+)")


@dataclass(frozen=True)
class ClickLine:
    job: str
    version: str
    user: str
    seq: int
    count: int


def parse(text: str) -> list[ClickLine]:
    return [ClickLine(m[1], m[2], m[3], int(m[4]), int(m[5])) for m in LINE.finditer(text)]


def last_per_user(lines: list[ClickLine]) -> dict[str, ClickLine]:
    out: dict[str, ClickLine] = {}
    for line in lines:
        out[line.user] = line
    return out


def first_per_user(lines: list[ClickLine]) -> dict[str, ClickLine]:
    out: dict[str, ClickLine] = {}
    for line in lines:
        out.setdefault(line.user, line)
    return out


def gaps(lines: list[ClickLine]) -> list[str]:
    seen: dict[str, int] = {}
    broken: list[str] = []
    for line in lines:
        previous = seen.get(line.user)
        if previous is not None and line.count != previous + 1:
            broken.append(f"{line.user}: {previous} -> {line.count}")
        seen[line.user] = line.count
    return broken
