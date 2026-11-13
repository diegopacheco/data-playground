import pytest

from etl.config import Settings
from etl.store import Commit, Ready, pending_batches


def test_only_batches_with_a_ready_marker_are_pending_so_half_written_input_is_never_read() -> None:
    inputs = ["input/s1-000001/part-0.jsonl", "input/s1-000001/_READY", "input/s1-000002/part-0.jsonl"]
    assert pending_batches(inputs, []) == ["s1-000001"]


def test_committed_batches_are_not_pending_so_each_batch_is_processed_once() -> None:
    inputs = ["input/s1-000001/_READY", "input/s1-000002/_READY", "input/s1-000003/_READY"]
    outputs = ["output/s1-000002/events/x.parquet", "output/s1-000002/_SUCCESS", "output/s1-000003/events/y.parquet"]
    assert pending_batches(inputs, outputs) == ["s1-000001", "s1-000003"]


def test_marker_files_nested_deeper_do_not_count_as_batch_markers() -> None:
    assert pending_batches(["input/s1-000001/sub/_READY"], []) == []


def test_ready_marker_from_the_java_producer_parses() -> None:
    text = '{"batch_id":"s1-000002","files":["input/s1-000002/part-0.jsonl"],"events":14,"ready_at_ms":1800000000000}'
    assert Ready.parse(text) == Ready("s1-000002", ("input/s1-000002/part-0.jsonl",), 14, 1800000000000)


def test_commit_json_carries_the_timestamps_latency_is_computed_from() -> None:
    assert Commit("b", 1, 2, 3, 4).to_json() == '{"batch_id": "b", "ready_at_ms": 1, "started_at_ms": 2, "committed_at_ms": 3, "rows": 4}'


def test_settings_reject_zero_parallelism() -> None:
    with pytest.raises(ValueError):
        Settings.from_env({"PARALLEL_BATCHES": "0"})
