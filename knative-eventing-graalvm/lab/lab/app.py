import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs

from lab.events import Sender, produce
from lab.store import Store

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
Asgi = Callable[[Scope, Receive, Send], Awaitable[None]]


async def read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            return b"".join(chunks)


async def respond(send: Send, status: int, payload: Any = None) -> None:
    body = b"" if payload is None else json.dumps(payload).encode()
    await send({"type": "http.response.start", "status": status, "headers": [(b"content-type", b"application/json")]})
    await send({"type": "http.response.body", "body": body})


def variant_of(scope: Scope) -> str:
    values = parse_qs(scope.get("query_string", b"").decode()).get("variant", [])
    if not values:
        raise ValueError("variant query parameter is required")
    return values[0]


def build(store: Store, sender: Sender, clock: Callable[[], int]) -> Asgi:
    async def route(scope: Scope, receive: Receive, send: Send) -> None:
        method, path = scope["method"], scope["path"]
        if (method, path) == ("POST", "/records"):
            store.add(json.loads(await read_body(receive)), clock())
            await respond(send, 204)
        elif (method, path) == ("GET", "/records"):
            await respond(send, 200, store.records_for(variant_of(scope)))
        elif (method, path) == ("DELETE", "/records"):
            store.reset(variant_of(scope))
            await respond(send, 204)
        elif (method, path) == ("POST", "/produce"):
            request = json.loads(await read_body(receive))
            produced = await asyncio.to_thread(produce, store, sender, clock, request["variant"], request["events"])
            await respond(send, 200, {"producedAtMs": produced})
        elif (method, path) == ("GET", "/health"):
            await respond(send, 200, {"status": "up"})
        else:
            await respond(send, 404, {})

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            while (await receive())["type"] != "lifespan.shutdown":
                await send({"type": "lifespan.startup.complete"})
            await send({"type": "lifespan.shutdown.complete"})
        elif scope["type"] == "http":
            await route(scope, receive, send)

    return app
