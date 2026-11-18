import sys

from pyspark.sql import SparkSession

from streamjob import iceberg_sink, kafka_events
from streamjob.args import parse


def main(argv: list[str]) -> None:
    args = parse(argv)
    spark = SparkSession.builder.appName(f"events-python {args.table}").getOrCreate()
    iceberg_sink.create_table(spark, args.table)
    query = iceberg_sink.start(kafka_events.parse(kafka_events.read(spark, args)), args.table, args.checkpoint, args.trigger_seconds)
    query.awaitTermination()


if __name__ == "__main__":
    main(sys.argv[1:])
