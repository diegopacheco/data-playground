import time
from collections.abc import Iterator
from dataclasses import asdict
from typing import Any

import pytest

from lake_e2e import config, kube, lake, results
from lake_e2e.stats import SweepPoint, summarize

POINTS: dict[tuple[str, int], SweepPoint] = {}


@pytest.fixture(scope="module", autouse=True)
def restore_defaults() -> Iterator[None]:
    kube.scale_producer(1)
    yield
    for lang in config.LANGS:
        kube.restore_app(lang)


def first_commits(tables: dict[str, str]) -> dict[str, int] | None:
    found: dict[str, int] = {}
    for lang, table in tables.items():
        if not lake.table_exists(table):
            return None
        rows = lake.query(lake.snapshots_sql(table))[0]
        if not rows:
            return None
        found[lang] = rows[0]["commit_ms"]
    return found


def measure(table: str, start_ms: int, end_ms: int, trigger: int) -> SweepPoint:
    def complete() -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
        latencies, snapshots = lake.query(lake.latency_sql(table), lake.snapshots_sql(table))
        return (latencies, snapshots) if snapshots and snapshots[-1]["commit_ms"] >= end_ms + trigger * 1000 else None

    latencies, snapshots = kube.wait_for(f"{table} commits after the window", complete, every=5)
    return summarize(latencies, snapshots, start_ms, end_ms)


@pytest.mark.parametrize("trigger", config.TRIGGERS)
def test_trigger_interval_sets_end_to_end_latency_and_the_number_of_iceberg_snapshots(trigger: int) -> None:
    stamp = int(time.time())
    tables = {lang: f"lake.db.sweep_{lang}_t{trigger}_{stamp}" for lang in config.LANGS}
    for lang, table in tables.items():
        kube.deploy_app(lang, table, f"s3a://checkpoints/{table.rsplit('.', 1)[1]}", trigger, "latest")

    first = kube.wait_for("first commit of both jobs", lambda: first_commits(tables), every=3)
    start_ms = max(first.values()) + config.WARMUP_SECONDS * 1000
    end_ms = start_ms + config.WINDOW_SECONDS * 1000
    time.sleep(config.WARMUP_SECONDS + config.WINDOW_SECONDS + trigger)

    for lang, table in tables.items():
        point = measure(table, start_ms, end_ms, trigger)
        POINTS[(lang, trigger)] = point
        results.record("sweep", lang, f"trigger={trigger}s", asdict(point))
        assert point.events >= 0.9 * config.RATE * config.WINDOW_SECONDS, f"{lang} lost events in the window: {point}"
        assert point.p50_ms >= 0


def test_longer_triggers_trade_latency_for_fewer_snapshots_and_bigger_files() -> None:
    shortest, longest = min(config.TRIGGERS), max(config.TRIGGERS)
    for lang in config.LANGS:
        fast, slow = POINTS[(lang, shortest)], POINTS[(lang, longest)]
        assert slow.p50_ms > fast.p50_ms, f"{lang}: {slow} vs {fast}"
        assert slow.snapshots_per_min < fast.snapshots_per_min, f"{lang}: {slow} vs {fast}"
        assert slow.avg_file_kb > fast.avg_file_kb, f"{lang}: {slow} vs {fast}"
