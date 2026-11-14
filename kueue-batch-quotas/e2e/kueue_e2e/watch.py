import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from kueue_e2e import config
from kueue_e2e.jobs import EtlJob, submit
from kueue_e2e.kube import cpu_milli, items


@dataclass(frozen=True)
class JobState:
    exists: bool
    admitted: bool
    finished: bool
    suspended: bool
    succeeded: int
    failed: int
    pods: int
    evictions: dict[str, int]
    pending_reason: str
    preempted_reason: str


@dataclass(frozen=True)
class QueueState:
    reserved_cpu_milli: int
    borrowed_cpu_milli: int
    weighted_share: int
    pending: int
    admitted: int


@dataclass(frozen=True)
class Snapshot:
    at: float
    jobs: dict[str, JobState]
    queues: dict[str, QueueState]


@dataclass(frozen=True)
class Event:
    at: float
    job: str
    kind: str


@dataclass
class Tracker:
    scenario: str
    run: str
    jobs: dict[str, EtlJob] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)
    max_admitted: dict[str, int] = field(default_factory=dict)
    max_borrowed: dict[str, int] = field(default_factory=dict)
    last: Snapshot | None = None

    def now(self) -> float:
        return round(time.monotonic() - self.started, 2)

    def submit(self, job: EtlJob) -> None:
        submit(job, self.run)
        self.jobs[job.name] = job
        self.events.append(Event(self.now(), job.name, "submitted"))

    def first(self, job: str, kind: str) -> float | None:
        return next((e.at for e in self.events if e.job == job and e.kind == kind), None)

    def times(self, job: str, kind: str) -> list[float]:
        return [e.at for e in self.events if e.job == job and e.kind == kind]

    def poll(self) -> Snapshot:
        snap = Snapshot(self.now(), self.job_states(), queue_states())
        self.record(snap)
        return snap

    def wait_for(self, what: str, check: Callable[[Snapshot], bool], timeout: float = config.SCENARIO_TIMEOUT_SECONDS) -> Snapshot:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            snap = self.poll()
            failed = [n for n, s in snap.jobs.items() if s.finished and s.succeeded == 0]
            if failed:
                raise AssertionError(f"{self.scenario}: jobs failed {failed}, see kubectl get events")
            if check(snap):
                return snap
            time.sleep(config.POLL_SECONDS)
        raise TimeoutError(f"{self.scenario}: timed out waiting for {what}, last state {self.last}")

    def wait_all_finished(self) -> Snapshot:
        return self.wait_for("every job finished", lambda s: all(s.jobs[n].finished for n in self.jobs))

    def job_states(self) -> dict[str, JobState]:
        workloads = {owner_job(w): w for w in items("workloads", "-A")}
        jobs = {j["metadata"]["name"]: j for j in items("jobs", "-A", "-l", f"etl-run={self.run}")}
        pods: dict[str, int] = {}
        for pod in items("pods", "-A", "-l", f"etl-run={self.run}"):
            name = pod["metadata"]["labels"].get("job-name", "")
            pods[name] = pods.get(name, 0) + 1
        return {n: job_state(jobs.get(n), workloads.get(n), pods.get(n, 0)) for n in self.jobs}

    def record(self, snap: Snapshot) -> None:
        previous = self.last.jobs if self.last else {}
        for name, state in snap.jobs.items():
            before = previous.get(name)
            if state.admitted and not (before and before.admitted):
                self.events.append(Event(snap.at, name, "admitted"))
            if before and before.admitted and not state.admitted and not state.finished:
                self.events.append(Event(snap.at, name, "evicted"))
            if state.finished and not (before and before.finished):
                self.events.append(Event(snap.at, name, "finished"))
        for queue, qs in snap.queues.items():
            self.max_borrowed[queue] = max(self.max_borrowed.get(queue, 0), qs.borrowed_cpu_milli)
            running = sum(1 for n, s in snap.jobs.items() if s.admitted and self.jobs[n].cluster_queue == queue)
            self.max_admitted[queue] = max(self.max_admitted.get(queue, 0), running)
        self.last = snap


def owner_job(workload: dict[str, Any]) -> str:
    owners = workload["metadata"].get("ownerReferences", [])
    return next((o["name"] for o in owners if o["kind"] == "Job"), "")


def condition(obj: dict[str, Any], kind: str) -> dict[str, Any] | None:
    return next((c for c in obj.get("status", {}).get("conditions", []) if c["type"] == kind), None)


def is_true(obj: dict[str, Any], kind: str) -> bool:
    cond = condition(obj, kind)
    return cond is not None and cond["status"] == "True"


def job_state(job: dict[str, Any] | None, workload: dict[str, Any] | None, pods: int) -> JobState:
    if job is None or workload is None:
        return JobState(False, False, False, True, 0, 0, pods, {}, "", "")
    stats = workload.get("status", {}).get("schedulingStats", {}).get("evictions", [])
    reserved = condition(workload, "QuotaReserved")
    preempted = condition(workload, "Preempted")
    return JobState(
        exists=True,
        admitted=is_true(workload, "Admitted") and not is_true(workload, "Finished"),
        finished=is_true(workload, "Finished"),
        suspended=bool(job["spec"].get("suspend", False)),
        succeeded=job.get("status", {}).get("succeeded", 0),
        failed=job.get("status", {}).get("failed", 0),
        pods=pods,
        evictions={f"{e['reason']}/{e.get('underlyingCause', '')}": e["count"] for e in stats},
        pending_reason=reserved["reason"] if reserved and reserved["status"] == "False" else "",
        preempted_reason=preempted["reason"] if preempted else "",
    )


def queue_states() -> dict[str, QueueState]:
    states: dict[str, QueueState] = {}
    for cq in items("clusterqueues"):
        status = cq.get("status", {})
        reserved = borrowed = 0
        for flavor in status.get("flavorsReservation", []):
            for res in flavor.get("resources", []):
                if res["name"] == "cpu":
                    reserved += cpu_milli(res.get("total", "0"))
                    borrowed += cpu_milli(res.get("borrowed", "0"))
        states[cq["metadata"]["name"]] = QueueState(
            reserved_cpu_milli=reserved,
            borrowed_cpu_milli=borrowed,
            weighted_share=int(status.get("fairSharing", {}).get("weightedShare", 0)),
            pending=status.get("pendingWorkloads", 0),
            admitted=status.get("admittedWorkloads", 0),
        )
    return states
