import time
from collections.abc import Iterator
from typing import Any

import pytest

from lake_e2e import config, kube, lake, results
from lake_e2e.stats import duplicate_epochs

KILLS = 2


@pytest.fixture(scope="module", autouse=True)
def restore_defaults() -> Iterator[None]:
    yield
    kube.scale_producer(1)
    for lang in config.LANGS:
        kube.restore_app(lang)


def snapshots(table: str) -> list[dict[str, Any]]:
    return lake.query(lake.snapshots_sql(table))[0] if lake.table_exists(table) else []


def wait_snapshots(table: str, at_least: int) -> list[dict[str, Any]]:
    return kube.wait_for(f"{at_least} snapshots in {table}", lambda: s if len(s := snapshots(table)) >= at_least else None, every=2)


def kill_and_wait_for_restart(lang: str) -> float:
    old = kube.wait_for("running driver", lambda: kube.running_driver_uid(lang))
    killed = time.monotonic()
    kube.kill_driver(lang)
    kube.wait_for("a new driver pod", lambda: uid if (uid := kube.running_driver_uid(lang)) and uid != old else None)
    restarted = time.monotonic() - killed
    kube.wait_for(f"events-{lang} RUNNING", lambda: True if kube.app_state(lang) == "RUNNING" else None)
    return restarted


@pytest.mark.parametrize("lang", config.LANGS)
def test_every_produced_event_lands_in_iceberg_exactly_once_across_driver_kills(lang: str) -> None:
    run = f"eo_{lang}_{int(time.time())}"
    table = f"lake.db.{run}"
    kube.scale_producer(1)
    kube.deploy_app(lang, table, f"s3a://checkpoints/{run}", 5, "earliest")
    attempts_before = kube.execution_attempts(lang)

    seen = len(wait_snapshots(table, 2))
    restarts = []
    for _ in range(KILLS):
        restarts.append(kill_and_wait_for_restart(lang))
        seen = len(wait_snapshots(table, seen + 2))

    kube.scale_producer(0)
    earliest = kube.kafka_offsets("-2")
    latest = kube.kafka_offsets("-1")
    expected = sum(latest[p] - earliest[p] for p in latest)

    def caught_up() -> dict[str, Any] | None:
        counts = lake.query(lake.counts_sql(table))[0][0]
        assert counts["total"] <= expected, f"more rows than produced events: {counts} > {expected}"
        return counts if counts["total"] == expected else None

    kube.wait_for(f"{table} to reach {expected} rows", caught_up, every=2)
    time.sleep(12)
    counts, partitions, snaps = lake.query(lake.counts_sql(table), lake.partitions_sql(table), lake.snapshots_sql(table))
    attempts_after = kube.execution_attempts(lang)

    assert counts[0] == {"total": expected, "ids": expected, "offsets": expected}
    assert {r["p"]: (r["lo"], r["hi"], r["n"]) for r in partitions} == {
        p: (earliest[p], latest[p] - 1, latest[p] - earliest[p]) for p in latest if latest[p] > earliest[p]
    }
    assert duplicate_epochs(snaps) == []
    assert len({s["query_id"] for s in snaps}) == 1, "the restarted driver resumed the same query from the checkpoint"
    assert attempts_after >= attempts_before + KILLS
    results.record(
        "exactly_once",
        lang,
        f"kills={KILLS}",
        {
            "events": expected,
            "rows": counts[0]["total"],
            "distinct_ids": counts[0]["ids"],
            "snapshots": len(snaps),
            "driver_restart_s": [round(r, 1) for r in restarts],
            "execution_attempts": attempts_after,
        },
    )
