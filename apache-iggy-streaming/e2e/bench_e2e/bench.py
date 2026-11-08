import json
import sys
from typing import Any

from bench_e2e import config
from bench_e2e.cluster import Run, run_job

SIZES = (100, 1024)
RATES = (1000, 10000)
HEADER = "| broker | client | size B | target msg/s | sent | received | complete | consumed msg/s | MB/s | p50 ms | p95 ms | p99 ms | max ms |"


def plan(seconds: int) -> list[Run]:
    runs = [
        Run(broker, client, rate, size, seconds)
        for size in SIZES
        for rate in RATES
        for client in config.CLIENTS
        for broker in config.BROKERS
    ]
    runs += [Run(broker, "java", 0, size, seconds) for size in SIZES for broker in config.BROKERS]
    return runs


def row(r: dict[str, Any]) -> str:
    lat = r["latency"]
    target = "max" if r["rate"] <= 0 else str(r["rate"])
    return (
        f"| {r['broker']} | {r['client']} | {r['size']} | {target} | {r['sent']} | {r['received']} | "
        f"{'yes' if r['complete'] else 'NO'} | {r['consume_rate']:.0f} | {r['mb_per_s']:.2f} | "
        f"{lat['p50_ms']:.2f} | {lat['p95_ms']:.2f} | {lat['p99_ms']:.2f} | {lat['max_ms']:.2f} |"
    )


def check(r: dict[str, Any]) -> None:
    if not r["complete"] or r["send_errors"] or r["ts_violations"]:
        raise SystemExit(f"run is not valid, refusing to report it: {json.dumps(r)}")


def main(seconds: int) -> None:
    results: list[dict[str, Any]] = []
    runs = plan(seconds)
    for i, run in enumerate(runs, start=1):
        print(f"{i}/{len(runs)} {run}", file=sys.stderr, flush=True)
        result = run_job(run)
        check(result)
        results.append(result)
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (config.RESULTS_DIR / "results.json").write_text(json.dumps(results, indent=1))
    print(HEADER)
    print("|" + "---|" * 13)
    for r in results:
        print(row(r))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 15)
