from collections import Counter

import pytest

from backfill_e2e import config, db
from backfill_e2e.cluster import delete_jobs, pods_by_index, run_job

ALL_INDEXES = set(range(config.PARTITIONS))
TRANSIENT_INDEX = 3
FATAL_INDEX = 5
type Truth = dict[db.AggregateKey, db.AggregateValue]


@pytest.fixture(params=config.WORKERS)
def worker(request: pytest.FixtureRequest) -> str:
    name: str = request.param
    delete_jobs(name)
    db.reset(name)
    return name


@pytest.fixture(scope="module")
def truth() -> Truth:
    expected = db.ground_truth()
    assert len({day for day, _ in expected}) == config.PARTITIONS
    return expected


def ok_indexes(run_id: str) -> Counter[int]:
    return Counter(r.idx for r in db.ledger(run_id) if r.status == "ok")


def test_every_partition_is_backfilled_exactly_once_and_matches_sql_ground_truth(worker: str, truth: Truth) -> None:
    job = run_job(worker, "once")
    assert job.condition == "Complete"
    assert job.status.get("succeeded") == config.PARTITIONS
    assert job.status.get("failed", 0) == 0
    assert db.aggregates(worker) == truth
    rows = db.ledger(job.name)
    assert ok_indexes(job.name) == Counter({i: 1 for i in ALL_INDEXES})
    assert len(rows) == config.PARTITIONS
    assert sum(r.rows_read for r in rows) == db.total_events()
    pods = pods_by_index(job.name)
    assert pods == {i: ["Succeeded"] for i in ALL_INDEXES}


def test_transient_failure_of_one_index_retries_only_that_index(worker: str, truth: Truth) -> None:
    job = run_job(worker, "retry", fail_index=TRANSIENT_INDEX)
    assert job.condition == "Complete"
    assert job.status.get("failed") == 1
    assert job.status.get("succeeded") == config.PARTITIONS
    rows = db.ledger(job.name)
    retried = [(r.attempt, r.status) for r in rows if r.idx == TRANSIENT_INDEX]
    assert retried == [(0, "transient"), (1, "ok")]
    others = [(r.idx, r.attempt, r.status) for r in rows if r.idx != TRANSIENT_INDEX]
    assert sorted(others) == [(i, 0, "ok") for i in sorted(ALL_INDEXES - {TRANSIENT_INDEX})]
    pods = pods_by_index(job.name)
    assert pods[TRANSIENT_INDEX] == ["Failed", "Succeeded"]
    assert {i: p for i, p in pods.items() if i != TRANSIENT_INDEX} == {
        i: ["Succeeded"] for i in ALL_INDEXES - {TRANSIENT_INDEX}
    }
    assert db.aggregates(worker) == truth
    assert db.aggregate_run_ids(worker) == {job.name}


def test_rerunning_the_whole_job_is_idempotent(worker: str, truth: Truth) -> None:
    first = run_job(worker, "first")
    assert first.condition == "Complete"
    after_first = db.aggregates(worker)
    second = run_job(worker, "second")
    assert second.condition == "Complete"
    assert ok_indexes(second.name) == Counter({i: 1 for i in ALL_INDEXES})
    assert db.aggregate_run_ids(worker) == {second.name}
    assert db.aggregates(worker) == after_first == truth


def test_fatal_error_fails_only_its_index_without_retry_and_others_still_complete(worker: str, truth: Truth) -> None:
    job = run_job(worker, "fatal", fatal_index=FATAL_INDEX)
    assert job.condition == "Failed"
    assert job.status.get("failedIndexes") == str(FATAL_INDEX)
    assert job.status.get("completedIndexes") == f"0-{FATAL_INDEX - 1},{FATAL_INDEX + 1}-{config.PARTITIONS - 1}"
    rows = db.ledger(job.name)
    assert [(r.attempt, r.status) for r in rows if r.idx == FATAL_INDEX] == [(0, "fatal")]
    assert ok_indexes(job.name) == Counter({i: 1 for i in ALL_INDEXES - {FATAL_INDEX}})
    assert pods_by_index(job.name)[FATAL_INDEX] == ["Failed"]
    fatal_day = sorted({day for day, _ in truth})[FATAL_INDEX]
    assert db.aggregates(worker) == {k: v for k, v in truth.items() if k[0] != fatal_day}
