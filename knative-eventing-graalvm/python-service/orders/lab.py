import json
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class HandledRecord:
    variant: str
    id: str
    sku: str
    total_cents: int
    pod: str
    started_at_ms: int
    ready_at_ms: int
    handled_at_ms: int
    rss_kb: int
    cgroup_bytes: int

    def to_json(self) -> bytes:
        return json.dumps(
            {
                "variant": self.variant,
                "id": self.id,
                "sku": self.sku,
                "totalCents": self.total_cents,
                "pod": self.pod,
                "startedAtMs": self.started_at_ms,
                "readyAtMs": self.ready_at_ms,
                "handledAtMs": self.handled_at_ms,
                "rssKb": self.rss_kb,
                "cgroupBytes": self.cgroup_bytes,
            }
        ).encode()


def report(lab_url: str, record: HandledRecord) -> None:
    request = urllib.request.Request(
        f"{lab_url}/records",
        data=record.to_json(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 204:
            raise RuntimeError(f"lab answered {response.status} for {record.id}")
