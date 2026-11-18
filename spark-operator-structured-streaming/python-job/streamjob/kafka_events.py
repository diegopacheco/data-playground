from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, from_json, timestamp_millis
from pyspark.sql.types import LongType, StringType, StructField, StructType

from streamjob.args import JobArgs

PAYLOAD = StructType(
    [
        StructField("id", StringType()),
        StructField("seq", LongType()),
        StructField("event_time_ms", LongType()),
    ]
)


def read(spark: SparkSession, args: JobArgs) -> DataFrame:
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", args.bootstrap)
        .option("subscribe", args.topic)
        .option("startingOffsets", args.starting_offsets)
        .option("failOnDataLoss", "true")
        .load()
    )


def parse(kafka_rows: DataFrame) -> DataFrame:
    decoded = kafka_rows.select(
        from_json(col("value").cast(StringType()), PAYLOAD).alias("e"),
        col("partition"),
        col("offset"),
    )
    return decoded.select(
        col("e.id").alias("id"),
        col("e.seq").alias("seq"),
        timestamp_millis(col("e.event_time_ms")).alias("event_time"),
        col("partition").alias("kafka_partition"),
        col("offset").alias("kafka_offset"),
    )
