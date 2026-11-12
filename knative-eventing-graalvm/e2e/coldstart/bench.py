import json
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from coldstart import cluster, config, lab
from coldstart.timeline import ColdStart, cold_start, median, p95, warm_latency_ms


@dataclass
class VariantRuns:
    variant: str
    image_mb: float
    cold: list[ColdStart] = field(default_factory=list)
    warm_ms: list[int] = field(default_factory=list)
    rss_mb: list[float] = field(default_factory=list)
    cgroup_mb: list[float] = field(default_factory=list)


def one_event(variant: str) -> lab.Record:
    orders = lab.make_orders(1)
    lab.produce(variant, orders)
    return lab.wait_records(variant, {orders[0]["id"]})[0]


def measure(runs: VariantRuns) -> None:
    first = one_event(runs.variant)
    runs.cold.append(cold_start(first))
    last = first
    for _ in range(config.WARM_EVENTS):
        last = one_event(runs.variant)
        if last["pod"] != first["pod"]:
            raise RuntimeError(f"{runs.variant}: warm event landed on another pod")
        runs.warm_ms.append(warm_latency_ms(last))
    runs.rss_mb.append(last["rssKb"] / 1024)
    runs.cgroup_mb.append(last["cgroupBytes"] / 1024 / 1024)
    print(f"  {runs.variant}: cold {runs.cold[-1]}, warm median {median(runs.warm_ms[-config.WARM_EVENTS:])} ms", flush=True)


def wait_all_zero() -> None:
    with ThreadPoolExecutor(len(config.VARIANTS)) as pool:
        list(pool.map(cluster.wait_for_zero, config.VARIANTS))


def summary(runs: VariantRuns) -> dict[str, float | str | int]:
    def stat(name: str, values: Sequence[float]) -> dict[str, float]:
        return {f"{name}_median": round(median(values), 1), f"{name}_p95": round(p95(values), 1)}

    return {
        "variant": runs.variant,
        "runs": len(runs.cold),
        "image_mb": round(runs.image_mb, 1),
        **stat("cold_total_ms", [c.total_ms for c in runs.cold]),
        **stat("scale_up_ms", [c.scale_up_ms for c in runs.cold]),
        **stat("app_start_ms", [c.app_start_ms for c in runs.cold]),
        **stat("first_request_ms", [c.first_request_ms for c in runs.cold]),
        **stat("warm_ms", runs.warm_ms),
        "rss_mb_median": round(median(runs.rss_mb), 1),
        "cgroup_mb_median": round(median(runs.cgroup_mb), 1),
    }


def table(rows: list[dict[str, float | str | int]]) -> str:
    lines = [
        "| Variant | Image MB | Cold total median / p95 ms | Scale-up median / p95 ms | App start median / p95 ms | First request median / p95 ms | Warm median / p95 ms | RSS MB | cgroup MB |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['variant']} | {r['image_mb']} | {r['cold_total_ms_median']} / {r['cold_total_ms_p95']} "
            f"| {r['scale_up_ms_median']} / {r['scale_up_ms_p95']} | {r['app_start_ms_median']} / {r['app_start_ms_p95']} "
            f"| {r['first_request_ms_median']} / {r['first_request_ms_p95']} | {r['warm_ms_median']} / {r['warm_ms_p95']} "
            f"| {r['rss_mb_median']} | {r['cgroup_mb_median']} |"
        )
    return "\n".join(lines)


def main(rounds: int) -> None:
    all_runs = {v: VariantRuns(v, cluster.image_size_mb(v)) for v in config.VARIANTS}
    for r in range(rounds):
        print(f"round {r + 1}/{rounds}: waiting until every service is at zero", flush=True)
        wait_all_zero()
        shift = r % len(config.VARIANTS)
        for variant in config.VARIANTS[shift:] + config.VARIANTS[:shift]:
            measure(all_runs[variant])
    rows = [summary(all_runs[v]) for v in config.VARIANTS]
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw = {v: {"cold": [asdict(c) for c in runs.cold], "warm_ms": runs.warm_ms} for v, runs in all_runs.items()}
    (config.RESULTS_DIR / "bench.json").write_text(json.dumps({"summary": rows, "raw": raw}, indent=2))
    print(table(rows))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
