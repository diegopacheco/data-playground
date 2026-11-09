from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event:
    id: int
    account: str
    amount_cents: int
    updated_at: datetime


@dataclass(frozen=True, order=True)
class Watermark:
    updated_at: datetime
    id: int

    @staticmethod
    def of(event: Event) -> Watermark:
        return Watermark(event.updated_at, event.id)

    def advance(self, page: Sequence[Event]) -> Watermark:
        return max([self, *(Watermark.of(e) for e in page)])
