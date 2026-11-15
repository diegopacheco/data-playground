import os
import time
import urllib.error
from dataclasses import dataclass
from typing import Any

from harness import http

JAEGER = os.environ.get("JAEGER_URL", "http://localhost:27701")
KINDS = {1: "internal", 2: "server", 3: "client", 4: "producer", 5: "consumer"}


@dataclass(frozen=True)
class Span:
    span_id: str
    parent_id: str | None
    name: str
    service: str
    kind: str
    tags: dict[str, str]


def attributes(raw: list[dict[str, Any]]) -> dict[str, str]:
    return {a["key"]: str(next(iter(a["value"].values()), "")) for a in raw}


def trace(trace_id: str) -> list[Span]:
    try:
        body = http.get(f"{JAEGER}/api/v3/traces/{trace_id}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise
    spans = []
    for resource_spans in body.get("result", {}).get("resourceSpans", []):
        service = attributes(resource_spans["resource"]["attributes"]).get("service.name", "")
        for scope in resource_spans.get("scopeSpans", []):
            for s in scope["spans"]:
                spans.append(
                    Span(
                        span_id=s["spanId"],
                        parent_id=s.get("parentSpanId") or None,
                        name=s["name"],
                        service=service,
                        kind=KINDS.get(int(s.get("kind", 0)), "unspecified"),
                        tags=attributes(s.get("attributes", [])),
                    )
                )
    return spans


def wait_for_trace(trace_id: str, services: set[str], min_spans: int, timeout: float = 60) -> list[Span]:
    deadline = time.monotonic() + timeout
    spans = trace(trace_id)
    while ({s.service for s in spans} < services or len(spans) < min_spans) and time.monotonic() < deadline:
        time.sleep(2)
        spans = trace(trace_id)
    return spans
