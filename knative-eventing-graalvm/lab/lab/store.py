import threading
from typing import Any

Record = dict[str, Any]


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._produced: dict[tuple[str, str], int] = {}
        self._records: list[Record] = []

    def mark_produced(self, variant: str, event_id: str, produced_at_ms: int) -> None:
        with self._lock:
            self._produced[(variant, event_id)] = produced_at_ms

    def add(self, record: Record, received_at_ms: int) -> None:
        with self._lock:
            self._records.append({**record, "receivedAtMs": received_at_ms})

    def records_for(self, variant: str) -> list[Record]:
        with self._lock:
            return [
                {**r, "producedAtMs": self._produced.get((variant, r["id"]))}
                for r in self._records
                if r["variant"] == variant
            ]

    def reset(self, variant: str) -> None:
        with self._lock:
            self._records = [r for r in self._records if r["variant"] != variant]
            self._produced = {k: v for k, v in self._produced.items() if k[0] != variant}
