import json
from dataclasses import asdict, dataclass

from streambench.config import BenchConfig
from streambench.recorder import Recorder
from streambench.stats import summarize


@dataclass(frozen=True)
class ProducerOutcome:
    sent: int
    send_errors: int
    started_at_us: int
    finished_at_us: int


def build(cfg: BenchConfig, producer: ProducerOutcome, recorder: Recorder, finished_at_us: int) -> dict[str, object]:
    tracker = recorder.tracker
    active_s = max(recorder.last_received_at_us - producer.started_at_us, 1) / 1_000_000
    send_s = max(producer.finished_at_us - producer.started_at_us, 1) / 1_000_000
    consume_rate = recorder.received / active_s
    return {
        "broker": cfg.broker,
        "client": "python",
        "rate": cfg.rate,
        "size": cfg.size,
        "seconds": cfg.seconds,
        "partitions": cfg.partitions,
        "sent": producer.sent,
        "received": recorder.received,
        "send_errors": producer.send_errors,
        "gaps": tracker.gaps,
        "backwards": tracker.backwards,
        "misrouted": tracker.misrouted,
        "in_order": tracker.in_order(),
        "complete": tracker.complete(producer.sent),
        "send_rate": round(producer.sent / send_s, 1),
        "consume_rate": round(consume_rate, 1),
        "mb_per_s": round(consume_rate * cfg.size / 1_000_000, 3),
        "latency": asdict(summarize(recorder.latencies_us)) if recorder.latencies_us else None,
        "ts_checked": recorder.ts_checked,
        "ts_violations": recorder.ts_violations,
        "run_started_us": producer.started_at_us,
        "run_finished_us": finished_at_us,
        "min_sent_at_us": recorder.min_sent_at_us,
        "max_sent_at_us": recorder.max_sent_at_us,
    }


def render(result: dict[str, object]) -> str:
    return "RESULT " + json.dumps(result, separators=(",", ":"))
