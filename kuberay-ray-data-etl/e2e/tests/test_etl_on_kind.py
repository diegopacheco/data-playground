import time
from collections.abc import Iterator

import pytest

from ray_e2e import config, kube, ray_state, results
from ray_e2e.results import percentile, seconds
from ray_e2e.s3 import Bucket
from ray_e2e.timeline import Watcher, cluster_clock_offset_ms, now_ms
from ray_e2e.truth import compare

BURST_BATCHES = 24
BURST_FILES = 8
BURST_EVENTS_PER_FILE = 25000


@pytest.fixture(scope="module")
def bucket() -> Iterator[Bucket]:
    assert kube.ray_job_status() == ("Running", "RUNNING"), "rayjob etl-driver must be running, run scripts/start-all.sh"
    results.reset()
    yield Bucket()
    kube.scale_producer(1)


def problems_for(bucket: Bucket, batch_ids: set[str]) -> list[str]:
    problems = []
    for batch_id in sorted(batch_ids):
        events = bucket.input_events(batch_id)
        problems += compare(batch_id, events, bucket.output_event_ids(batch_id), bucket.output_aggregates(batch_id))
    return problems


def assert_committed_once(batch_ids: set[str]) -> None:
    counts = ray_state.commit_counts(ray_state.driver_log())
    wrong = {b: counts[b] for b in batch_ids if counts[b] != 1}
    assert wrong == {}, f"batches not committed exactly once by the driver: {wrong}"


def wait_committed(bucket: Bucket, run_id: str, count: int) -> set[str]:
    def probe() -> set[str] | None:
        done = {b for b in bucket.committed() if b.startswith(run_id + "-")}
        return done if len(done) == count else None

    return kube.wait_for(f"{count} batches of {run_id} committed", probe)


def wait_min_workers() -> None:
    kube.wait_for("workers back at minReplicas", lambda: True if len(kube.live_worker_pods()) == config.MIN_WORKERS else None, 240)


def burst(run_id: str) -> set[str]:
    name = kube.start_burst(run_id, BURST_BATCHES, BURST_FILES, BURST_EVENTS_PER_FILE)
    kube.wait_for(f"{name} succeeded", lambda: True if kube.job_succeeded(name) else None)
    return {f"{run_id}-{seq:06d}" for seq in range(1, BURST_BATCHES + 1)}


def test_every_steady_microbatch_is_processed_exactly_once_and_matches_ground_truth(bucket: Bucket) -> None:
    kube.wait_for("6 steady batches committed", lambda: True if len({b for b in bucket.committed() if b.startswith("s")}) >= 6 else None, 120)
    kube.scale_producer(0)
    kube.wait_for("no pending batches", lambda: True if bucket.ready() <= bucket.committed() else None, 120)
    ready = bucket.ready()
    committed = bucket.committed()
    assert committed == ready, f"output without input: {committed - ready}"
    assert problems_for(bucket, ready) == []
    assert_committed_once(ready)
    commits = [bucket.commit(b) for b in sorted(ready) if b.startswith("s")]
    latency = [c["committed_at_ms"] - c["ready_at_ms"] for c in commits]
    processing = [c["committed_at_ms"] - c["started_at_ms"] for c in commits]
    results.table(
        "Steady microbatches (1 batch every 5 s, 4 files x 250 events)",
        ["batches", "rows out", "ready -> committed p50 (s)", "p95 (s)", "max (s)", "processing p50 (s)", "processing max (s)"],
        [[len(commits), sum(c["rows"] for c in commits), seconds(percentile(latency, 0.5)), seconds(percentile(latency, 0.95)), seconds(max(latency)), seconds(percentile(processing, 0.5)), seconds(max(processing))]],
    )


def test_a_burst_scales_workers_up_and_idle_workers_are_removed(bucket: Bucket) -> None:
    wait_min_workers()
    offset = cluster_clock_offset_ms()
    run_id = f"a{int(time.time())}"
    with Watcher(offset) as watcher:
        t0 = now_ms() + offset
        batch_ids = burst(run_id)
        wait_committed(bucket, run_id, BURST_BATCHES)
        wait_min_workers()
        time.sleep(2)
    assert watcher.errors == []
    commits = [bucket.commit(b) for b in batch_ids]
    first_ready = min(c["ready_at_ms"] for c in commits)
    last_commit = max(c["committed_at_ms"] for c in commits)
    pending_at = watcher.first_pending_ms(t0)
    new_pods = [p for p in watcher.pods.values() if p.created_ms >= t0 - 1000]
    new_nodes = {n.ip: n for n in ray_state.nodes() if n.start_ms >= t0}
    assert pending_at is not None, "no task ever waited for a node"
    assert 2 <= watcher.max_live() <= config.MAX_WORKERS
    assert len(new_pods) == watcher.max_live() - config.MIN_WORKERS
    rows = []
    for pod in sorted(new_pods, key=lambda p: p.created_ms):
        node = new_nodes.get(pod.ip)
        assert node is not None, f"{pod.name} never joined the ray cluster"
        assert pod.scheduled_ms is not None and pod.ready_ms is not None
        assert pending_at <= node.start_ms, f"{pod.name} joined before any task was pending"
        assert not node.alive and node.end_ms > last_commit, f"{pod.name} was not removed after the burst"
        ran = ray_state.tasks_on(node.node_id)
        assert ran > 0, f"{pod.name} joined but ran no task"
        rows.append([pod.name, seconds(pending_at - first_ready), seconds(pod.created_ms - first_ready), seconds(pod.scheduled_ms - first_ready), seconds(pod.ready_ms - first_ready), seconds(node.start_ms - first_ready), ran, seconds(last_commit - first_ready), seconds(node.end_ms - first_ready), seconds(node.end_ms - last_commit)])
    assert problems_for(bucket, batch_ids) == []
    assert_committed_once(batch_ids)
    results.table(
        f"Autoscaling timeline, burst of {BURST_BATCHES} batches x {BURST_FILES * BURST_EVENTS_PER_FILE} events, seconds after the first burst batch was READY",
        ["new worker", "first pending task", "pod created", "pod scheduled", "pod ready", "ray node joined", "tasks run", "burst last commit", "node removed", "removed after last commit"],
        rows,
    )


def test_killing_a_worker_mid_burst_neither_loses_nor_duplicates_output(bucket: Bucket) -> None:
    offset = cluster_clock_offset_ms()
    run_id = f"k{int(time.time())}"
    name = kube.start_burst(run_id, BURST_BATCHES, BURST_FILES, BURST_EVENTS_PER_FILE)

    def busy_worker() -> tuple[str, str] | None:
        running = ray_state.running_task_nodes()
        ips = {n.ip: n.node_id for n in ray_state.nodes() if n.alive and n.node_id in running}
        pod = next((p for p in kube.live_worker_pods() if p["status"].get("podIP") in ips), None)
        if pod is None or not any(b.startswith(run_id) for b in bucket.ready()):
            return None
        return pod["metadata"]["name"], ips[pod["status"]["podIP"]]

    victim, victim_node = kube.wait_for("a worker running burst tasks", busy_worker, 120)
    retried_before = len(ray_state.retried_tasks())
    kube.delete_pod(victim)
    killed_at = now_ms() + offset
    kube.wait_for(f"{name} succeeded", lambda: True if kube.job_succeeded(name) else None)
    batch_ids = {f"{run_id}-{seq:06d}" for seq in range(1, BURST_BATCHES + 1)}
    wait_committed(bucket, run_id, BURST_BATCHES)
    assert kube.ray_job_status() == ("Running", "RUNNING"), "driver died with the worker"
    commits = [bucket.commit(b) for b in batch_ids]
    in_flight = sorted(c["batch_id"] for c in commits if c["started_at_ms"] <= killed_at <= c["committed_at_ms"])
    assert in_flight, "no batch was in flight when the worker died, the kill proved nothing"
    retried = len(ray_state.retried_tasks()) - retried_before
    assert retried > 0, "ray reported no retried task attempt after the worker died"
    assert problems_for(bucket, batch_ids) == []
    assert_committed_once(batch_ids)
    dead = next(n for n in ray_state.nodes() if n.node_id == victim_node)
    first_ready = min(c["ready_at_ms"] for c in commits)
    last_commit = max(c["committed_at_ms"] for c in commits)
    results.table(
        "Worker pod killed mid burst",
        ["killed after first READY (s)", "batches in flight at kill", "task attempts retried after kill", "node marked dead after kill (s)", "kill -> last commit (s)", "burst total (s)", "lost or duplicated events"],
        [[seconds(killed_at - first_ready), len(in_flight), retried, seconds(dead.end_ms - killed_at if dead.end_ms else None), seconds(last_commit - killed_at), seconds(last_commit - first_ready), 0]],
    )
