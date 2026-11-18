import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    id: str
    seq: int
    event_time_ms: int

    def encode(self) -> bytes:
        return json.dumps({"id": self.id, "seq": self.seq, "event_time_ms": self.event_time_ms}, separators=(",", ":")).encode()


def event(source: str, seq: int, now_ms: int) -> Event:
    return Event(f"{source}-{seq}", seq, now_ms)


def due(start: float, seq: int, rate: int) -> float:
    return start + seq / rate
