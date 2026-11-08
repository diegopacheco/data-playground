import struct
import time
from dataclasses import dataclass

HEADER = struct.Struct(">QQ")
MIN_SIZE = HEADER.size


@dataclass(frozen=True)
class Stamp:
    seq: int
    sent_at_us: int


def now_us() -> int:
    return time.time_ns() // 1000


def encode(seq: int, sent_at_us: int, size: int) -> bytes:
    if size < MIN_SIZE:
        raise ValueError(f"message size {size} is below the {MIN_SIZE} byte header")
    return HEADER.pack(seq, sent_at_us) + bytes(size - MIN_SIZE)


def decode(data: bytes) -> Stamp:
    seq, sent_at_us = HEADER.unpack_from(data)
    return Stamp(seq, sent_at_us)
