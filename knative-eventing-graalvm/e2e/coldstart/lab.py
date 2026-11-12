import json
import time
import urllib.request
import uuid
from typing import Any

from coldstart import config

Record = dict[str, Any]
Order = dict[str, Any]


def call(method: str, path: str, body: Any = None) -> Any:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(f"{config.LAB_URL}{path}", data=data, method=method)
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def make_orders(count: int) -> list[Order]:
    return [
        {"id": str(uuid.uuid4()), "sku": f" sku-{i % 7} ", "quantity": 1 + i % 5, "unitPriceCents": 100 + i}
        for i in range(count)
    ]


def produce(variant: str, orders: list[Order]) -> list[int]:
    return call("POST", "/produce", {"variant": variant, "events": orders})["producedAtMs"]


def records(variant: str) -> list[Record]:
    return call("GET", f"/records?variant={variant}")


def reset(variant: str) -> None:
    call("DELETE", f"/records?variant={variant}")


def wait_records(variant: str, ids: set[str], timeout_s: float = config.RECORD_TIMEOUT_S) -> list[Record]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        found = [r for r in records(variant) if r["id"] in ids]
        if {r["id"] for r in found} >= ids:
            return found
        time.sleep(0.05)
    raise TimeoutError(f"{variant}: only {len({r['id'] for r in records(variant)} & ids)} of {len(ids)} events handled")
