from datetime import datetime

from pyspark.sql import Row

from streamjob.query import plain


def test_query_rows_become_json_safe_so_the_e2e_tests_can_parse_snapshot_summaries_and_timestamps() -> None:
    row = Row(committed_at=datetime(2026, 1, 1, 0, 0, 5), summary={"added-data-files": "1"}, ids=[1, 2])
    assert plain(row) == {"committed_at": "2026-01-01T00:00:05", "summary": {"added-data-files": "1"}, "ids": [1, 2]}
