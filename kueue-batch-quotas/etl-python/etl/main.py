import os
import time

from etl.config import EtlConfig
from etl.sink import mark_started, result_row, write_result
from etl.transform import summarize


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def main() -> None:
    cfg = EtlConfig.from_env(os.environ)
    started = now_ms()
    mark_started(cfg, started)
    summary = summarize(cfg.rows, cfg.seed, cfg.rounds)
    path = write_result(cfg, result_row(cfg, summary, "python", started, now_ms()))
    print(f"wrote {path} digest={summary.digest}", flush=True)


if __name__ == "__main__":
    main()
