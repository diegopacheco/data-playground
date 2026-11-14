import time
from collections.abc import Iterator

import pytest

from etl.transform import Summary
from kueue_e2e import config, report
from kueue_e2e.jobs import run_id
from kueue_e2e.kube import items, kubectl
from kueue_e2e.results import expected_by_seed
from kueue_e2e.watch import Tracker


@pytest.fixture(scope="session")
def expected() -> dict[int, Summary]:
    return expected_by_seed()


@pytest.fixture(scope="session")
def trackers() -> Iterator[list[Tracker]]:
    for namespace, _ in config.TEAMS.values():
        kubectl("-n", namespace, "delete", "jobs", "-l", "app=etl", "--ignore-not-found", "--cascade=foreground", "--wait=true")
    for _ in range(60):
        if not items("workloads", "-A"):
            break
        time.sleep(1)
    assert not items("workloads", "-A"), "workloads left from an earlier run"
    collected: list[Tracker] = []
    yield collected
    report.write(collected)


@pytest.fixture
def tracker(request: pytest.FixtureRequest, trackers: list[Tracker]) -> Tracker:
    t = Tracker(request.node.name.removeprefix("test_").replace("_", " "), run_id())
    trackers.append(t)
    return t
