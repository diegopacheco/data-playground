from pyspark.sql import Row, SparkSession
from pyspark.sql.types import BinaryType, IntegerType, LongType, StructField, StructType

from streamjob.kafka_events import parse

KAFKA = StructType(
    [
        StructField("value", BinaryType()),
        StructField("partition", IntegerType()),
        StructField("offset", LongType()),
    ]
)


def parsed(spark: SparkSession, payload: str, partition: int, offset: int) -> Row:
    frame = spark.createDataFrame([(bytearray(payload.encode()), partition, offset)], KAFKA)
    return parse(frame).collect()[0]


def test_event_time_comes_from_the_payload_so_latency_is_measured_from_when_the_event_happened(spark: SparkSession) -> None:
    row = parsed(spark, '{"id":"p-7","seq":7,"event_time_ms":1767225600123}', 1, 42)
    assert row["id"] == "p-7"
    assert row["seq"] == 7
    assert round(row["event_time"].timestamp() * 1000) == 1767225600123


def test_partition_and_offset_are_kept_so_every_row_traces_back_to_exactly_one_kafka_record(spark: SparkSession) -> None:
    row = parsed(spark, '{"id":"p-1","seq":1,"event_time_ms":1}', 1, 42)
    assert row["kafka_partition"] == 1
    assert row["kafka_offset"] == 42
