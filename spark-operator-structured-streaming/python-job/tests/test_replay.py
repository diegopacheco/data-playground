from pathlib import Path

import pytest
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.streaming import StreamingQuery

from streamjob import iceberg_sink

ROWS = 50
EVENTS = "id STRING, seq BIGINT, event_time TIMESTAMP, kafka_partition INT, kafka_offset BIGINT"


@pytest.fixture(scope="module")
def source_dir(root: Path) -> Path:
    path = root / "input"
    path.mkdir()
    lines = [
        f'{{"id":"p-{i}","seq":{i},"event_time":"2026-01-01T00:00:00Z","kafka_partition":0,"kafka_offset":{i}}}'
        for i in range(ROWS)
    ]
    (path / "part-0.json").write_text("\n".join(lines))
    return path


def source(spark: SparkSession, source_dir: Path) -> DataFrame:
    return spark.readStream.schema(EVENTS).json(str(source_dir))


def crash_after_sink_commit(checkpoint: Path) -> None:
    (checkpoint / "commits" / "0").unlink()
    (checkpoint / "commits" / ".0.crc").unlink(missing_ok=True)


def run_once(query: StreamingQuery) -> None:
    query.awaitTermination()


def distinct_offsets(spark: SparkSession, table: str) -> int:
    return spark.table(table).select("kafka_partition", "kafka_offset").distinct().count()


def test_a_batch_replayed_after_a_crash_between_iceberg_commit_and_spark_commit_log_is_not_written_twice(
    spark: SparkSession, root: Path, source_dir: Path
) -> None:
    table = "lake.db.idempotent"
    checkpoint = root / "cp-idempotent"
    iceberg_sink.create_table(spark, table)
    run_once(iceberg_sink.start(source(spark, source_dir), table, checkpoint.as_uri(), None))
    assert spark.table(table).count() == ROWS

    crash_after_sink_commit(checkpoint)
    run_once(iceberg_sink.start(source(spark, source_dir), table, checkpoint.as_uri(), None))

    assert (checkpoint / "commits" / "0").exists()
    assert spark.table(table).count() == ROWS
    assert distinct_offsets(spark, table) == ROWS
    assert spark.sql(f"SELECT count(*) AS n FROM {table}.snapshots").collect()[0]["n"] == 1


def test_a_plain_append_in_foreach_batch_duplicates_the_same_replay_which_is_why_the_iceberg_streaming_sink_is_used(
    spark: SparkSession, root: Path, source_dir: Path
) -> None:
    table = "lake.db.plain_append"
    checkpoint = root / "cp-plain"
    iceberg_sink.create_table(spark, table)

    def plain_append() -> StreamingQuery:
        return (
            source(spark, source_dir)
            .writeStream.trigger(availableNow=True)
            .option("checkpointLocation", checkpoint.as_uri())
            .foreachBatch(lambda batch, _: batch.writeTo(table).append())
            .start()
        )

    run_once(plain_append())
    crash_after_sink_commit(checkpoint)
    run_once(plain_append())

    assert spark.table(table).count() == 2 * ROWS
    assert distinct_offsets(spark, table) == ROWS
