import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from orders import probe
from orders.lab import HandledRecord
from orders.transform import apply, parse_event

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
Asgi = Callable[[Scope, Receive, Send], Awaitable[None]]
Reporter = Callable[[HandledRecord], None]


@dataclass
class Runtime:
    variant: str
    pod: str
    started_at_ms: int
    ready_at_ms: int = -1


async def read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            return b"".join(chunks)


async def respond(send: Send, status: int, body: bytes) -> None:
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


async def lifespan(runtime: Runtime, receive: Receive, send: Send) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            runtime.ready_at_ms = probe.now_ms()
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


def build(runtime: Runtime, reporter: Reporter, memory: Callable[[], tuple[int, int]]) -> Asgi:
    async def handle(receive: Receive, send: Send) -> None:
        order = apply(parse_event(await read_body(receive)))
        rss, cgroup = memory()
        record = HandledRecord(
            variant=runtime.variant,
            id=order.id,
            sku=order.sku,
            total_cents=order.total_cents,
            pod=runtime.pod,
            started_at_ms=runtime.started_at_ms,
            ready_at_ms=runtime.ready_at_ms,
            handled_at_ms=probe.now_ms(),
            rss_kb=rss,
            cgroup_bytes=cgroup,
        )
        await asyncio.to_thread(reporter, record)
        await respond(send, 200, json.dumps({"id": order.id, "sku": order.sku, "totalCents": order.total_cents}).encode())

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await lifespan(runtime, receive, send)
        elif scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == "/":
            await handle(receive, send)
        elif scope["type"] == "http":
            await respond(send, 404, b"{}")

    return app
