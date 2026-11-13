import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ray_e2e import kube, ray_state


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def k8s_ms(stamp: str) -> int:
    return int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000)


def condition_ms(pod: dict[str, Any], kind: str) -> int | None:
    for c in pod.get("status", {}).get("conditions", []):
        if c["type"] == kind and c["status"] == "True":
            return k8s_ms(c["lastTransitionTime"])
    return None


def cluster_clock_offset_ms() -> int:
    head = kube.pods("ray.io/node-type=head")[0]["metadata"]["name"]
    before = now_ms()
    remote = int(kube.kubectl("exec", head, "-c", "ray-head", "--", "date", "+%s%3N").strip())
    return remote - (before + now_ms()) // 2


@dataclass
class PodTrace:
    name: str
    ip: str
    created_ms: int
    scheduled_ms: int | None
    ready_ms: int | None
    last_seen_ms: int


@dataclass
class Watcher:
    offset_ms: int
    pending: list[tuple[int, int]] = field(default_factory=list)
    live: list[tuple[int, int]] = field(default_factory=list)
    pods: dict[str, PodTrace] = field(default_factory=dict)
    stop: threading.Event = field(default_factory=threading.Event)
    errors: list[str] = field(default_factory=list)

    def sample(self) -> None:
        t = now_ms() + self.offset_ms
        self.pending.append((t, ray_state.count_tasks("PENDING_NODE_ASSIGNMENT")))
        live = kube.live_worker_pods()
        self.live.append((t, len(live)))
        for p in live:
            name = p["metadata"]["name"]
            self.pods[name] = PodTrace(
                name,
                p["status"].get("podIP", ""),
                k8s_ms(p["metadata"]["creationTimestamp"]),
                condition_ms(p, "PodScheduled"),
                condition_ms(p, "Ready"),
                t,
            )

    def loop(self) -> None:
        while not self.stop.is_set():
            try:
                self.sample()
            except RuntimeError as e:
                self.errors.append(str(e))
            self.stop.wait(1)

    def __enter__(self) -> "Watcher":
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop.set()
        self.thread.join()

    def first_pending_ms(self, after_ms: int) -> int | None:
        return next((t for t, n in self.pending if t >= after_ms and n > 0), None)

    def max_live(self) -> int:
        return max((n for _, n in self.live), default=0)
