from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.streaming import StreamingQuery


def create_table(spark: SparkSession, table: str) -> None:
    spark.sql(
        f"CREATE TABLE IF NOT EXISTS {table}"
        " (id STRING, seq BIGINT, event_time TIMESTAMP, kafka_partition INT, kafka_offset BIGINT)"
        " USING iceberg TBLPROPERTIES ('format-version'='2')"
    )


def start(events: DataFrame, table: str, checkpoint: str, trigger_seconds: int | None) -> StreamingQuery:
    writer = events.writeStream.format("iceberg").outputMode("append").option("checkpointLocation", checkpoint).queryName(table)
    if trigger_seconds is None:
        writer = writer.trigger(availableNow=True)
    else:
        writer = writer.trigger(processingTime=f"{trigger_seconds} seconds")
    return writer.toTable(table)
