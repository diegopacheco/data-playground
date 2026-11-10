import pytest

from flink_e2e import config, kube
from flink_e2e.clicks import first_per_user, gaps, last_per_user
from flink_e2e.upgrade import NAMES, Transition, deploy_fresh, operator_state, record, transition, with_version

KINDS = ["java", "python"]


def assert_counts_continue(t: Transition) -> None:
    before = last_per_user(t.before)
    after = first_per_user(t.after)
    assert set(before) == set(after) and len(after) == config.USERS
    for user, last in before.items():
        assert after[user].count == last.count + 1, f"{t.kind} {t.label}: {user} was {last.count} before, {after[user].count} after"
        assert after[user].seq == last.seq + config.USERS, f"{t.kind} {t.label}: {user} source skipped or replayed clicks"
    assert gaps(t.before) == [] and gaps(t.after) == []


def assert_restored_from_savepoint(t: Transition) -> None:
    assert t.restored is not None, f"{t.kind} {t.label}: new job was not restored from anything"
    assert t.restored["is_savepoint"] is True
    assert "/savepoints/" in t.restored["external_path"]


@pytest.fixture(scope="module", autouse=True)
def baseline_after_tests():
    config.RESULTS.unlink(missing_ok=True)
    yield
    for kind in KINDS:
        deploy_fresh(kind, "savepoint")


@pytest.mark.parametrize("kind", KINDS)
def test_savepoint_upgrade_of_the_job_spec_keeps_every_user_count(kind: str) -> None:
    name = deploy_fresh(kind, "savepoint")
    args = kube.deployment(name)["spec"]["job"]["args"]
    t = transition(kind, "upgrade v1->v2", {"args": with_version(args, "v2")})
    record(t)
    assert {line.version for line in t.before} == {"v1"}
    assert {line.version for line in t.after} == {"v2"}
    assert_restored_from_savepoint(t)
    assert_counts_continue(t)


@pytest.mark.parametrize("kind", KINDS)
def test_rescale_one_to_two_to_one_restores_the_same_counts_from_savepoints(kind: str) -> None:
    deploy_fresh(kind, "savepoint")
    up = transition(kind, "rescale 1->2", {"parallelism": 2})
    record(up)
    assert up.parallelism == 2
    assert_restored_from_savepoint(up)
    assert_counts_continue(up)
    down = transition(kind, "rescale 2->1", {"parallelism": 1})
    record(down)
    assert down.parallelism == 1
    assert_restored_from_savepoint(down)
    assert_counts_continue(down)


@pytest.mark.parametrize("kind", KINDS)
def test_stateless_upgrade_loses_the_counts_and_starts_over(kind: str) -> None:
    name = deploy_fresh(kind, "stateless")
    args = kube.deployment(name)["spec"]["job"]["args"]
    t = transition(kind, "upgrade v1->v2", {"args": with_version(args, "v2")})
    record(t)
    before = last_per_user(t.before)
    after = first_per_user(t.after)
    assert min(line.count for line in before.values()) > 1
    assert t.restored is None
    assert {line.count for line in after.values()} == {1}, f"{kind}: stateless upgrade unexpectedly kept state"
    assert sorted(line.seq for line in after.values()) == list(range(config.USERS))


def test_the_operator_reports_both_jobs_running_after_their_last_upgrade() -> None:
    for name in NAMES.values():
        assert kube.wait_for(f"{name} running in operator status", lambda: operator_state(name) == "RUNNING" or None)
        assert kube.deployment(name)["status"]["reconciliationStatus"]["state"] == "DEPLOYED"
