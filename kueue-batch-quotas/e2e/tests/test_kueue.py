import time

from etl.transform import Summary
from kueue_e2e import config
from kueue_e2e.jobs import make
from kueue_e2e.results import attempts
from kueue_e2e.watch import Snapshot, Tracker

PREEMPTED = "Preempted/"
COHORT_RECLAIM_CAUSES = ("InCohortReclamation", "InCohortFairSharing", "InCohortReclaimWhileBorrowing")
MAX_SLOTS_WITH_BORROWING = 2 * config.SLOTS_PER_TEAM
QUEUE_STATUS_SECONDS = 30


def admitted(snap: Snapshot, names: list[str]) -> list[str]:
    return [n for n in names if snap.jobs[n].admitted]


def queued(snap: Snapshot, names: list[str]) -> list[str]:
    return [n for n in names if snap.jobs[n].exists and not snap.jobs[n].admitted and not snap.jobs[n].finished]


def preemptions(snap: Snapshot, name: str) -> dict[str, int]:
    return {k: v for k, v in snap.jobs[name].evictions.items() if k.startswith(PREEMPTED)}


def assert_completed_exactly_once(tracker: Tracker, expected: dict[int, Summary]) -> None:
    snap = tracker.poll()
    for name, job in tracker.jobs.items():
        state = snap.jobs[name]
        assert state.finished and state.succeeded == 1 and state.failed == 0, f"{name}: {state}"
        runs = attempts(name)
        assert len(runs.results) == 1, f"{name} wrote {len(runs.results)} results"
        row = runs.results[0]
        want = expected[job.seed]
        assert (row["worker"], row["team"], row["rows"], row["seed"]) == (job.worker, job.team, job.rows, job.seed)
        assert row["digest"] == want.digest and row["totals"] == want.totals, f"{name} computed a wrong result"
        assert row["pod"] in runs.started
        evictions = sum(state.evictions.values())
        assert 1 <= len(runs.started) <= 1 + evictions, f"{name}: {len(runs.started)} attempts, {evictions} evictions"


def test_a_jobs_beyond_quota_wait_suspended_in_the_queue_and_are_admitted_in_submit_order(tracker: Tracker, expected: dict[int, Summary]) -> None:
    workers = ["python", "python", "java", "java", "python"]
    jobs = [make(tracker.run, i, "reports", w) for i, w in enumerate(workers)]
    names = [j.name for j in jobs]
    for job in jobs:
        tracker.submit(job)
        tracker.poll()
        time.sleep(1.1)

    snap = tracker.wait_for(
        "quota full, the rest queued, head of the queue waiting for quota",
        lambda s: len(admitted(s, names)) == config.SLOTS_PER_TEAM and len(queued(s, names)) == 3 and s.jobs[names[2]].pending_reason == "WaitingForQuota",
    )
    assert admitted(snap, names) == names[:2], "the first two submitted jobs must hold the quota"
    for name in queued(snap, names):
        state = snap.jobs[name]
        assert state.suspended, f"{name} must stay a suspended Job while it waits"
        assert state.pods == 0, f"{name} must not create Pending pods while it waits for quota"
    tracker.wait_for(
        "reports-cq status shows a full quota and 3 pending",
        lambda s: s.queues["reports-cq"].pending == 3 and s.queues["reports-cq"].reserved_cpu_milli == config.NOMINAL_CPU_MILLI,
        timeout=QUEUE_STATUS_SECONDS,
    )

    tracker.wait_all_finished()
    assert tracker.max_admitted["reports-cq"] == config.SLOTS_PER_TEAM, "admitted work never exceeds the nominal quota"
    first_admits = [tracker.first(n, "admitted") or 0.0 for n in names]
    assert first_admits == sorted(first_admits), f"admission order {first_admits} differs from submit order"
    finishes = sorted(tracker.first(n, "finished") or 0.0 for n in names)
    for k in range(2, len(names)):
        assert first_admits[k] >= finishes[k - 2], f"{names[k]} was admitted before quota was freed"
    assert_completed_exactly_once(tracker, expected)


def test_b_a_team_borrows_idle_quota_from_the_cohort_and_gives_it_back_when_the_owner_needs_it(tracker: Tracker, expected: dict[int, Summary]) -> None:
    finance = [make(tracker.run, i, "finance", "python") for i in range(4)]
    analytics = [make(tracker.run, 10 + i, "analytics", w) for i, w in enumerate(["java", "python"])]
    fin, ana = [j.name for j in finance], [j.name for j in analytics]
    for job in finance:
        tracker.submit(job)

    tracker.wait_for("finance runs 4 jobs", lambda s: len(admitted(s, fin)) == 4)
    snap = tracker.wait_for(
        "finance-cq status shows 2 own slots plus 2 borrowed from idle analytics",
        lambda s: s.queues["finance-cq"].reserved_cpu_milli == 2 * config.NOMINAL_CPU_MILLI and s.queues["finance-cq"].borrowed_cpu_milli == config.NOMINAL_CPU_MILLI,
        timeout=QUEUE_STATUS_SECONDS,
    )
    assert len(admitted(snap, fin)) == 4
    assert snap.queues["analytics-cq"].reserved_cpu_milli == 0
    tracker.wait_for("finance share above its fair share", lambda s: s.queues["finance-cq"].weighted_share > 0, timeout=QUEUE_STATUS_SECONDS)
    tracker.wait_for("every finance job started work", lambda s: all(attempts(n).started for n in fin))

    for job in analytics:
        tracker.submit(job)
    tracker.wait_for("analytics reclaims its quota", lambda s: len(admitted(s, ana)) == 2)
    snap = tracker.wait_for(
        "finance gave the borrowed quota back",
        lambda s: s.queues["finance-cq"].borrowed_cpu_milli == 0 and s.queues["analytics-cq"].reserved_cpu_milli == config.NOMINAL_CPU_MILLI,
        timeout=QUEUE_STATUS_SECONDS,
    )
    assert snap.queues["analytics-cq"].borrowed_cpu_milli == 0
    assert len(admitted(snap, fin)) == config.SLOTS_PER_TEAM, "finance keeps its own nominal quota"
    victims = [n for n in fin if preemptions(snap, n)]
    assert len(victims) == 2, f"exactly the 2 borrowed slots are reclaimed, got {victims}"
    for name in victims:
        assert snap.jobs[name].preempted_reason in COHORT_RECLAIM_CAUSES, f"{name} preempted for {snap.jobs[name].preempted_reason}"

    tracker.wait_all_finished()
    for name in victims:
        assert len(tracker.times(name, "admitted")) == 2, f"{name} must be requeued and admitted again"
        assert len(attempts(name).started) == 2, f"{name} must have restarted after the reclaim"
    tracker.wait_for("no quota stays borrowed after the work is done", lambda s: s.queues["finance-cq"].reserved_cpu_milli == 0, timeout=QUEUE_STATUS_SECONDS)
    assert tracker.max_borrowed["finance-cq"] == config.NOMINAL_CPU_MILLI, "borrowing stops at the borrowing limit"
    assert_completed_exactly_once(tracker, expected)


def test_c_a_high_priority_job_preempts_a_low_priority_job_which_is_requeued_and_finishes(tracker: Tracker, expected: dict[int, Summary]) -> None:
    lows = [make(tracker.run, i, "reports", "python") for i in range(2)]
    high = make(tracker.run, 5, "reports", "java", "etl-high")
    low_names = [j.name for j in lows]
    for job in lows:
        tracker.submit(job)
    tracker.wait_for("both low jobs running", lambda s: len(admitted(s, low_names)) == 2 and all(attempts(n).started for n in low_names))

    tracker.submit(high)
    snap = tracker.wait_for("high priority job admitted", lambda s: s.jobs[high.name].admitted)
    victims = [n for n in low_names if preemptions(snap, n)]
    assert len(victims) == 1, f"one slot is needed so exactly one low job is preempted, got {victims}"
    victim = victims[0]
    assert preemptions(snap, victim) == {PREEMPTED: 1}
    assert snap.jobs[victim].preempted_reason == "InClusterQueue", "preempted by priority inside its own ClusterQueue"
    assert not snap.jobs[victim].admitted and snap.jobs[victim].suspended, "the preempted job goes back to the queue suspended"
    assert not preemptions(snap, high.name)
    high_wait = (tracker.first(high.name, "admitted") or 0.0) - (tracker.first(high.name, "submitted") or 0.0)
    assert high_wait < 15, f"high priority job waited {high_wait}s"

    tracker.wait_all_finished()
    readmits = tracker.times(victim, "admitted")
    assert len(readmits) == 2 and readmits[1] > (tracker.first(high.name, "admitted") or 0.0)
    assert len(attempts(victim).started) == 2, "the preempted attempt was killed and the job ran again"
    assert tracker.max_admitted["reports-cq"] == config.SLOTS_PER_TEAM
    assert_completed_exactly_once(tracker, expected)


def test_d_every_submitted_job_completes_exactly_once_with_the_correct_result(tracker: Tracker, trackers: list[Tracker], expected: dict[int, Summary]) -> None:
    teams = ["analytics", "finance", "reports"]
    for i in range(9):
        priority = "etl-high" if i % 4 == 3 else "etl-low"
        tracker.submit(make(tracker.run, i, teams[i % 3], ["python", "java"][i % 2], priority))
    tracker.wait_all_finished()
    assert tracker.max_admitted["reports-cq"] <= config.SLOTS_PER_TEAM
    assert tracker.max_admitted["analytics-cq"] <= MAX_SLOTS_WITH_BORROWING
    assert tracker.max_admitted["finance-cq"] <= MAX_SLOTS_WITH_BORROWING
    for t in trackers:
        assert_completed_exactly_once(t, expected)
    total = sum(len(t.jobs) for t in trackers)
    workers = {j.worker for t in trackers for j in t.jobs.values()}
    assert total == 23 and workers == {"python", "java"}
