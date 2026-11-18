import pytest

from lake_e2e.lake import parse_rows
from lake_e2e.stats import duplicate_epochs, percentile, summarize


def test_percentile_uses_nearest_rank_so_p95_is_a_latency_that_was_really_observed() -> None:
    values = list(range(1, 101))
    assert percentile(values, 0.5) == 50
    assert percentile(values, 0.95) == 95
    assert percentile([7], 0.95) == 7
    with pytest.raises(ValueError):
        percentile([], 0.5)


def test_an_epoch_committed_twice_by_the_same_query_is_reported_because_that_would_be_a_duplicate_batch() -> None:
    snapshots = [{"query_id": "q", "epoch": 1}, {"query_id": "q", "epoch": 2}, {"query_id": "q", "epoch": 2}, {"query_id": "r", "epoch": 1}]
    assert duplicate_epochs(snapshots) == [("q", 2)]


def test_only_events_and_commits_inside_the_window_count_so_startup_backlog_does_not_skew_latency() -> None:
    latencies = [
        {"event_ms": 500, "commit_ms": 90_000},
        {"event_ms": 1_000, "commit_ms": 2_000},
        {"event_ms": 2_000, "commit_ms": 5_000},
        {"event_ms": 61_000, "commit_ms": 99_000},
    ]
    snapshots = [
        {"commit_ms": 2_000, "files": 2, "bytes": 4096, "records": 1},
        {"commit_ms": 5_000, "files": 2, "bytes": 4096, "records": 1},
        {"commit_ms": 70_000, "files": 2, "bytes": 4096, "records": 1},
    ]
    point = summarize(latencies, snapshots, 1_000, 61_000)
    assert point.events == 2
    assert point.p50_ms == 1_000
    assert point.max_ms == 3_000
    assert point.snapshots_per_min == 2.0
    assert point.files_per_min == 4.0
    assert point.avg_file_kb == 2.0


def test_query_output_is_split_per_statement_and_spark_log_lines_are_ignored() -> None:
    output = "WARN something\nROW 0 {\"a\": 1}\nROW 1 {\"b\": 2}\nROW 0 {\"a\": 3}\n"
    assert parse_rows(output, 2) == [[{"a": 1}, {"a": 3}], [{"b": 2}]]
