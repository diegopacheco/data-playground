import json
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime

from backfill_e2e import config, db
from backfill_e2e.cluster import delete_jobs, kubectl, run_job


@dataclass(frozen=True)
class Round:
    wall: float
    work: list[float]
    pod: list[float]


def pod_seconds(job: str) -> list[float]:
    pods = json.loads(kubectl("get", "pods", "-l", f"batch.kubernetes.io/job-name={job}", "-o", "json"))["items"]
    out: list[float] = []
    for pod in pods:
        term = pod["status"]["containerStatuses"][0]["state"]["terminated"]
        start = datetime.fromisoformat(term["startedAt"])
        end = datetime.fromisoformat(term["finishedAt"])
        out.append((end - start).total_seconds())
    return out


def bench_round(worker: str) -> Round:
    delete_jobs(worker)
    db.reset(worker)
    job = run_job(worker, "bench")
    if job.condition != "Complete":
        raise RuntimeError(f"{job.name} ended {job.condition}")
    if db.aggregates(worker) != db.ground_truth():
        raise RuntimeError(f"{job.name} aggregates do not match ground truth")
    return Round(job.wall_seconds, [r.seconds for r in db.ledger(job.name)], pod_seconds(job.name))


def summary(worker: str, rounds: list[Round]) -> str:
    walls = [r.wall for r in rounds]
    work = [s for r in rounds for s in r.work]
    pod = [s for r in rounds for s in r.pod]
    return (
        f"| {worker} | {statistics.median(walls):.1f} | {min(walls):.1f} | {max(walls):.1f} "
        f"| {statistics.mean(work):.2f} | {statistics.median(work):.2f} | {max(work):.2f} "
        f"| {statistics.mean(pod):.1f} |"
    )


def main() -> None:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    results: dict[str, list[Round]] = {w: [] for w in config.WORKERS}
    for i in range(rounds):
        for worker in config.WORKERS:
            r = bench_round(worker)
            results[worker].append(r)
            print(f"round {i + 1} {worker}: wall={r.wall:.1f}s per-index mean={statistics.mean(r.work):.2f}s", flush=True)
    print(f"{config.PARTITIONS} partitions, parallelism {config.PARALLELISM}, {config.SUBRANGES} sub-ranges, {rounds} rounds")
    print("| worker | job wall median s | wall min s | wall max s | per-index work mean s | per-index work median s | per-index work max s | per-index pod runtime mean s |")
    print("|---|---|---|---|---|---|---|---|")
    for worker, rs in results.items():
        print(summary(worker, rs))


if __name__ == "__main__":
    main()
