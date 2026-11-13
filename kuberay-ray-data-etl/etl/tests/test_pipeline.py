import json
from collections.abc import Iterator
from pathlib import Path

import pyarrow.parquet as pq
import pytest
import ray
from pyarrow import fs

from etl.driver import configure_ray_data
from etl.pipeline import process
from etl.store import Store


@pytest.fixture(scope="module", autouse=True)
def local_ray() -> Iterator[None]:
    ray.init(num_cpus=2, include_dashboard=False)
    configure_ray_data()
    yield
    ray.shutdown()


def event(i: int, category: str, amount: int) -> str:
    return json.dumps({"event_id": f"e{i}", "batch_id": "s1-000001", "user_id": f"user-{i % 3}", "category": category, "amount_cents": amount, "ts": 1})


@pytest.fixture
def store(tmp_path: Path) -> Store:
    store = Store(fs.LocalFileSystem(), str(tmp_path))
    rows = [event(0, "Books", 100), event(1, " books", 50), event(2, "MUSIC", 7), event(3, "music", -3)]
    store.fs.create_dir(store.path("input/s1-000001"))
    store.write_text("input/s1-000001/part-0.jsonl", "\n".join(rows[:2]) + "\n")
    store.write_text("input/s1-000001/part-1.jsonl", "\n".join(rows[2:]) + "\n")
    marker = {"batch_id": "s1-000001", "files": ["input/s1-000001/part-0.jsonl", "input/s1-000001/part-1.jsonl"], "events": 4, "ready_at_ms": 1}
    store.write_text("input/s1-000001/_READY", json.dumps(marker))
    return store


def aggregates(store: Store) -> list[tuple[str, int, int, int]]:
    table = pq.read_table(store.path("output/s1-000001/aggregates"), filesystem=store.fs)
    return sorted(zip(table["category"].to_pylist(), table["events"].to_pylist(), table["amount_cents"].to_pylist(), table["max_amount_cents"].to_pylist()))


def test_batch_aggregates_match_the_cleaned_input_and_commit_marks_it_done(store: Store) -> None:
    commit = process(store, store.ready("s1-000001"))
    assert aggregates(store) == [("books", 2, 150, 100), ("music", 1, 7, 7)]
    assert commit.rows == 3
    assert store.pending() == []


def test_reprocessing_a_batch_after_a_crash_replaces_output_instead_of_duplicating_it(store: Store) -> None:
    process(store, store.ready("s1-000001"))
    store.fs.delete_file(store.path("output/s1-000001/_SUCCESS"))
    assert store.pending() == ["s1-000001"]
    process(store, store.ready("s1-000001"))
    events = pq.read_table(store.path("output/s1-000001/events"), filesystem=store.fs)
    assert sorted(events["event_id"].to_pylist()) == ["e0", "e1", "e2"]
    assert aggregates(store) == [("books", 2, 150, 100), ("music", 1, 7, 7)]
